import logging

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _enable_edi_oca_enable_snippet(self, exchange_type):
        self.ensure_one()
        return (
            self._is_l10n_co_electronic_document_enabled()
            and not self._has_exchange_record(exchange_type)
        )

    def _is_l10n_co_electronic_document_enabled(self):
        """Verifica si esta activo el uso de documentos en la empresa"""
        return (
            self.journal_id.l10n_latam_use_documents
            and self.company_id.account_fiscal_country_id.code == "CO"
            and self.l10n_latam_document_type_id
        )

    def _l10n_co_electronic_document_customization_id(self):
        if not self.journal_id._is_support_document_type():
            return self.l10n_latam_document_type_id.code
        return (
            "10" if self.partner_id.commercial_partner_id.country_code == "CO" else "11"
        )

    def _get_colombian_formatted_sequence(self, number=0):
        if self.l10n_latam_document_type_id.code in ["01", "02", "03"]:
            prefix, start_number, _end_number = (
                self.journal_id._get_electronic_document_numbering_range()
            )
            return "%s%d" % (prefix, start_number + number)

        prefix = self.l10n_latam_document_type_id.doc_code_prefix
        start_number = 1
        return "%s%d" % (prefix, start_number + number)

    def _get_starting_sequence(self):
        if self._is_l10n_co_electronic_document_enabled():
            return self._get_colombian_formatted_sequence(0)
        return super()._get_starting_sequence()

    def _get_next_sequence_format(self):
        """Override to handle custom start number
        for Colombian electronic invoices"""
        if not self._is_l10n_co_electronic_document_enabled():
            return super()._get_next_sequence_format()

        last_sequence = self._get_last_sequence()
        config = self._get_colombian_electronic_invoice_config()

        # Verificar si se alcanzó el límite máximo autorizado
        self._check_sequence_limit_reached(last_sequence, config)

        # Determinar si es una nueva secuencia
        is_new_sequence = self._should_start_new_sequence(last_sequence, config)

        if is_new_sequence:
            return self._create_new_sequence_format(config)

        return super()._get_next_sequence_format()

    def _get_colombian_electronic_invoice_config(self):
        """Obtiene la configuración de facturación electrónica del diario"""
        if self.l10n_latam_document_type_id.code in ["01", "02", "03"]:
            prefix, start_number, end_number = (
                self.journal_id._get_electronic_document_numbering_range()
            )
            return {
                "prefix": prefix,
                "start_number": start_number,
                "end_number": end_number,
            }
        return {
            "prefix": self.l10n_latam_document_type_id.doc_code_prefix,
            "start_number": 1,
            "end_number": None,
        }

    def _check_sequence_limit_reached(self, last_sequence, config):
        """Verifica si se alcanzó el límite máximo de numeración autorizada"""
        if not (
            last_sequence
            and config["end_number"]
            and last_sequence.startswith(config["prefix"])
        ):
            return

        try:
            last_number = self._extract_sequence_number(last_sequence, config["prefix"])
            if last_number >= config["end_number"]:
                raise UserError(
                    _(
                        f"""Se ha alcanzado el número final autorizado
                        ({config["end_number"]}) para la facturación
                        electrónica en el diario {self.journal_id.name}.
                        Por favor, configure un nuevo rango de numeración
                        o contacte al administrador del sistema.
                        """
                    )
                )
        except (ValueError, AttributeError):
            _logger.warning(
                "Error al parsear el " f"número de secuencia: {last_sequence}"
            )
            pass  # Continuar con el flujo normal si hay error al parsear

    def _should_start_new_sequence(self, last_sequence, config):
        """Determina si debe iniciar una nueva secuencia"""
        if not last_sequence:
            return True

        # Verificar si tiene el mismo prefijo
        if not last_sequence.startswith(config["prefix"]):
            return True

        # Verificar si está dentro del rango configurado
        if config["end_number"]:
            try:
                last_number = self._extract_sequence_number(
                    last_sequence, config["prefix"]
                )
                if (
                    last_number < config["start_number"]
                    or last_number > config["end_number"]
                ):
                    return True
            except (ValueError, AttributeError):
                return True

        return False

    def _extract_sequence_number(self, sequence, prefix):
        """Extrae el número de secuencia de una cadena de secuencia"""
        seq_part = sequence.replace(prefix, "").strip()
        return int(seq_part)

    def _create_new_sequence_format(self, config):
        """Crea el formato para una nueva secuencia con número de inicio
        personalizado"""
        starting_sequence = self._get_starting_sequence()
        format_string, format_values = self._get_sequence_format_param(
            starting_sequence
        )
        sequence_number_reset = self._deduce_sequence_number_reset(starting_sequence)
        date_start, date_end, forced_year_start, forced_year_end = (
            self._get_sequence_date_range(sequence_number_reset)
        )

        # Configurar el número de secuencia para empezar desde el número
        # de inicio
        format_values["seq"] = config["start_number"] - 1
        format_values["year"] = self._truncate_year_to_length(
            forced_year_start or date_start.year, format_values["year_length"]
        )
        format_values["year_end"] = self._truncate_year_to_length(
            forced_year_end or date_end.year, format_values["year_end_length"]
        )
        format_values["month"] = self[self._sequence_date_field].month

        return format_string, format_values

    def _get_last_sequence_domain(self, relaxed=False):
        where_string, param = super()._get_last_sequence_domain(relaxed)
        if (
            self.company_id.account_fiscal_country_id.code == "CO"
            and self.l10n_latam_use_documents
        ):
            where_string += (
                " AND l10n_latam_document_type_id = " "%(l10n_latam_document_type_id)s"
            )
            param["l10n_latam_document_type_id"] = (
                self.l10n_latam_document_type_id.id or 0
            )
        return where_string, param

    def _verify_required_fields_electronic_document(self):
        self.ensure_one()
        errors = []

        journal_params = self.journal_id._get_l10n_co_dian_self_params()
        if not all(journal_params):
            errors.append(
                _(
                    "❖ Diario:Debe configurar el rango de numeración \
de la facturación electrónica."
                )
            )
        company_params = self.company_id._get_l10n_co_dian_self_params()
        if not all(company_params):
            errors.append(
                _(
                    "❖ La empresa: Debe configurar los parámetros fiscales de \
para la generacion de documentos electrónicos"
                )
            )

        partner_params = self.partner_id._get_l10n_co_dian_self_params()
        if not all(partner_params):
            errors.append(
                _(
                    "❖ Cliente: Debe configurar los parámetros fiscales \
para la generacion de documentos electrónicos"
                )
            )

        move_line_params = self.line_ids._get_l10n_co_dian_self_params()
        if len(move_line_params) == 0 or not all(move_line_params):
            errors.append(
                _(
                    "❖ Productos: Deben tener configurados los parámetros \
fiscales de para la generación de documentos electrónicos \
(codigo UNSPSC, impuesto, unidad de medida)"
                )
            )

        certificate = self.env["certificate.certificate"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("is_valid", "=", True),
                ("active", "=", True),
            ]
        )
        if not certificate:
            errors.append(
                _("❖ La empresa debe tener configurado un certificado válido")
            )

        if errors:
            raise ValidationError("\n".join(errors))
        return

    def _post(self, soft=True):
        result = super()._post(soft=soft)
        for move in self:
            if move.l10n_latam_document_type_id:
                move._verify_required_fields_electronic_document()
        return result
