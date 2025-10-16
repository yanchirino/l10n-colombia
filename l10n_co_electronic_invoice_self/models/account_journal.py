import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _name = "account.journal"
    _inherit = ["account.journal", "edi.exchange.consumer.mixin"]

    # DIAN - Modo de Operación
    l10n_co_dian_operation_mode = fields.Selection(
        selection=[("production", "Producción"), ("test", "Habilitación")],
        default="test",
        required=True,
        string="Modo de Operación",
    )

    # DIAN - Información del software
    l10n_co_dian_software_identification = fields.Char(string="Identificación")
    l10n_co_dian_software_pin = fields.Char(string="Pin")

    # Production values
    l10n_co_dian_resolution_type = fields.Selection(
        selection=[
            ("FACTURA ELECTRÓNICA DE VENTA", "FACTURA ELECTRÓNICA DE VENTA"),
            ("FACTURA D.E./P.O.S.", "FACTURA D.E. / P.O.S."),
            ("FACTURA POR TALONARIO O DE PAPEL", "FACTURA POR TALONARIO O DE PAPEL"),
            ("DOCUMENTO SOPORTE", "DOCUMENTO SOPORTE"),
        ],
        string="Tipo de Resolución",
        copy=False,
        help="Corresponde al tipo de resolución de la factura",
    )
    l10n_co_dian_software_technical_key = fields.Char(
        string="Clave técnica (Producción)"
    )
    l10n_co_electronic_document_prefix = fields.Char(string="Prefijo")
    l10n_co_electronic_document_start_number = fields.Integer(string="Número de Inicio")
    l10n_co_electronic_document_end_number = fields.Integer(string="Número de Fin")
    l10n_co_electronic_document_resolution = fields.Char(string="Resolución")
    l10n_co_electronic_document_start_resolution_date = fields.Date(
        string="Fecha de Inicio de Resolución"
    )
    l10n_co_electronic_document_end_resolution_date = fields.Date(
        string="Fecha de Fin de Resolución"
    )
    l10n_co_electronic_document_message = fields.Text(string="Mensaje de Resolución")

    # Test values (Habilitación)
    l10n_co_dian_resolution_type_test = fields.Selection(
        selection=[
            ("FACTURA ELECTRÓNICA DE VENTA", "FACTURA ELECTRÓNICA DE VENTA"),
            ("FACTURA D.E./P.O.S.", "FACTURA D.E. / P.O.S."),
            ("FACTURA POR TALONARIO O DE PAPEL", "FACTURA POR TALONARIO O DE PAPEL"),
            ("DOCUMENTO SOPORTE", "DOCUMENTO SOPORTE"),
        ],
        string="Tipo de Resolución (Habilitación)",
        copy=False,
        default="FACTURA ELECTRÓNICA DE VENTA",
        help="Corresponde al tipo de resolución de la factura (Habilitación)",
    )
    l10n_co_electronic_document_resolution_test = fields.Char(
        string="Resolución", default="000000000"
    )
    l10n_co_dian_software_technical_key_test = fields.Char(
        string="Clave Técnica (Habilitación)"
    )
    l10n_co_electronic_document_prefix_test = fields.Char(string="Prefijo")
    l10n_co_electronic_document_start_number_test = fields.Integer(
        string="Número de Inicio"
    )
    l10n_co_electronic_document_end_number_test = fields.Integer(string="Número de Fin")
    l10n_co_electronic_document_start_resolution_date_test = fields.Date(
        string="Fecha de Inicio de Resolución"
    )
    l10n_co_electronic_document_end_resolution_date_test = fields.Date(
        string="Fecha de Fin de Resolución"
    )
    l10n_co_electronic_document_message_test = fields.Text(
        string="Mensaje de Resolución"
    )

    def _enable_edi_oca_enable_snippet(self):
        self.ensure_one()
        return (
            self.l10n_co_dian_operation_mode == "production"
            and self.l10n_latam_use_documents
        )

    def _is_support_document_type(self):
        self.ensure_one()
        resolution_type = self.l10n_co_dian_resolution_type
        if self.l10n_co_dian_operation_mode != "production":
            resolution_type = self.l10n_co_dian_resolution_type_test
        return resolution_type == ["DOCUMENTO SOPORTE"] and self.type == "purchase"

    def _get_electronic_document_dates(self):
        self.ensure_one()
        if self.l10n_co_dian_operation_mode == "production":
            return (
                self.l10n_co_electronic_document_start_resolution_date,
                self.l10n_co_electronic_document_end_resolution_date,
            )
        return (
            self.l10n_co_electronic_document_start_resolution_date_test,
            self.l10n_co_electronic_document_end_resolution_date_test,
        )

    def _get_electronic_document_numbering_range(self):
        self.ensure_one()
        if self.l10n_co_dian_operation_mode == "production":
            return (
                self.l10n_co_electronic_document_prefix,
                self.l10n_co_electronic_document_start_number,
                self.l10n_co_electronic_document_end_number,
            )
        else:
            return (
                self.l10n_co_electronic_document_prefix_test,
                self.l10n_co_electronic_document_start_number_test,
                self.l10n_co_electronic_document_end_number_test,
            )

    def _get_l10n_co_dian_self_params(self):
        self.ensure_one()
        if self.l10n_co_dian_operation_mode == "production":
            return (
                self.l10n_co_dian_operation_mode,
                self.l10n_co_dian_software_identification,
                self.l10n_co_dian_software_pin,
                self.l10n_co_dian_software_technical_key,
                self.l10n_co_electronic_document_resolution,
                self.l10n_co_electronic_document_start_resolution_date,
                self.l10n_co_electronic_document_end_resolution_date,
                self.l10n_co_electronic_document_start_number,
                self.l10n_co_electronic_document_end_number,
            )
        else:
            return (
                self.l10n_co_dian_operation_mode,
                self.l10n_co_dian_software_identification,
                self.l10n_co_dian_software_pin,
                self.l10n_co_dian_software_technical_key_test,
                self.l10n_co_electronic_document_resolution_test,
                self.l10n_co_electronic_document_start_resolution_date_test,
                self.l10n_co_electronic_document_end_resolution_date_test,
                self.l10n_co_electronic_document_start_number_test,
                self.l10n_co_electronic_document_end_number_test,
            )
