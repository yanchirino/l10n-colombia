# Copyright 2025 IKU Solutions - Yan Chirino <yan.chirino@iku.solutions>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import base64
import io
import logging
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha384

import pytz
import xmltodict
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import frozendict

from odoo.addons.account_edi_ubl_cii.models.account_edi_xml_ubl_20 import FloatFmt

from ..utils.constants import (
    BUYER_NOT_IDENTIFIED_VAT,
    PROFILE_ID,
    SCHEMES,
    UUID_SCHEME_NAME,
)
from ..utils.xml_sign import XMLSigner

_logger = logging.getLogger(__name__)


class L10nCoDianSelfOutputHandler(models.AbstractModel):
    _name = "l10n_co.dian.self.output_handler"
    _description = "Handler to generate XML UBL and sign it for DIAN Colombia"
    _inherit = [
        "edi.oca.handler.generate",
        "edi.oca.handler.send",
        "account.edi.xml.ubl_21",
    ]

    def generate(self, exchange_record):
        """
        Generar XML UBL y firmarlo para DIAN Colombia.

        :return: XML firmado listo para envío
        """
        try:
            # 1. Preparar el signer para firmar el/los XML/s
            certificate = self._get_certificate(exchange_record)
            public_cert, private_key = self._get_certificate_and_key(certificate)
            signer = XMLSigner(exchange_record, public_cert, private_key)

            # 2. Generar XML UBL base
            if exchange_record.record._name == "account.journal":
                xml_content = self._generate_xml_content(exchange_record)
            else:
                generation_date = datetime.now()
                exchange_record.record.l10n_co_dian_generation_date = generation_date
                xml_content, errors = self._export_invoice_new(exchange_record.record)
                if errors:
                    # Informar los errores del diccionario de errores
                    raise ValidationError(
                        _("Error al generar XML UBL:\n%s") % "\n".join(errors.values())
                    )
                xml_content = self._fill_dian_data(xml_content, exchange_record.record)

            # 3. Firmar el XML si es necesario
            if exchange_record.type_id.l10n_co_dian_document_requires_signature:
                xml_content = signer._document_sign(xml_content)
                _logger.info(
                    "XML Content generado y firmado exitosamente para exchange %s",
                    exchange_record.identifier,
                )

            # 4. Generar el envelope XML
            soap_envelope = self._generate_soap_envelope(exchange_record, xml_content)
            soap_envelope = signer._envelope_sign(soap_envelope)
            _logger.info(
                "Envelope XML generado y firmado exitosamente para exchange %s",
                exchange_record.identifier,
            )
            return soap_envelope
        except Exception as e:
            _logger.error("Error al generar XML/s firmado/s: %s", str(e))
            raise UserError(_("Error al generar XML/s firmado/s: %s") % str(e)) from e

    def send(self, exchange_record):
        method, pargs, kwargs = (
            "post",
            [],
            {"data": exchange_record._get_file_content()},
        )
        result = exchange_record.backend_id.webservice_backend_id.call(
            method, *pargs, **kwargs
        )
        data = self.process(exchange_record, result)
        exchange_record.exchange_create_ack_record(
            **{
                "exchange_file": base64.b64encode(result).decode("utf-8"),
                "edi_exchange_state": "input_processed",
                "exchanged_on": data.get("create_date", fields.Datetime.now()),
            }
        )
        exchange_record.write({"edi_exchange_state": "output_sent_and_processed"})
        return True

    def process(self, exchange_record, result):
        values = xmltodict.parse(result)
        data = getattr(self, f"_{exchange_record.type_id.code}_response_process")(
            exchange_record.record, values
        )
        return data

    ######### UTILS #########
    #########################
    def _generate_xml_content(self, exchange_record):
        """Generar contenido XML para el envío."""
        tmpl = exchange_record.backend_id._get_output_template(exchange_record)
        if not tmpl:
            raise ValidationError(
                _("No se encontro la plantilla de generacion del documento XML")
            )
        exchange_record = exchange_record.with_context(edi_framework_action="generate")
        tmpl = tmpl.with_context(edi_framework_action="generate")
        xml_content = tmpl.exchange_generate(exchange_record)
        return xml_content.decode("utf-8")

    def _generate_soap_envelope(self, exchange_record, xml_content):
        """Generar el envelope SOAP para el envío."""
        created_time, expires_time = self._get_security_timestamp()
        body = (
            xml_content
            if not exchange_record.type_id.l10n_co_dian_body_zipped
            else self._zip_xml_content(
                xml_content, f"{exchange_record.record.name}.xml"
            )
        )
        soap_envelope = self.env["ir.qweb"]._render(
            "l10n_co_electronic_invoice_self.dian_soap_envelope",
            {
                "to_id": f"id-{uuid.uuid1()}",
                "to": exchange_record.backend_id.webservice_backend_id.url,
                "timestamp_id": f"TS-{uuid.uuid1()}",
                "created": created_time,
                "expires": expires_time,
                "action": exchange_record.type_id.l10n_co_dian_webservice_action,
                "body": body,
            },
        )
        return str(soap_envelope)

    def _get_security_timestamp(self, expires=5):
        created_dt = datetime.now(pytz.UTC)
        expires_dt = created_dt + timedelta(minutes=expires)
        created_time = created_dt.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        expires_time = expires_dt.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        return created_time, expires_time

    def _zip_content(self, content, name):
        """Comprimir el contenido XML en un zip y devolver base64."""
        content_bytes = content.encode("utf-8")
        zip_buffer = io.BytesIO()

        # Crear un archivo zip en memoria
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(name, content_bytes)

        zip_content = zip_buffer.getvalue()
        return base64.b64encode(zip_content).decode("utf-8")

    def _get_certificate(self, exchange_record):
        """Obtener certificado válido de la empresa."""
        company = exchange_record.record.company_id
        certificate = self.env["certificate.certificate"].search(
            [
                ("company_id", "=", company.id),
                ("is_valid", "=", True),
                ("active", "=", True),
            ],
            limit=1,
        )

        if not certificate:
            raise UserError(_("No se encontró certificado válido para firmar el XML"))

        if not certificate.is_valid:
            raise UserError(_("El certificado no es válido o ha expirado"))

        if not certificate.private_key_id:
            raise UserError(_("No hay clave privada asociada al certificado"))

        return certificate

    def _get_certificate_and_key(self, certificate):
        """Obtener certificado público y clave privada."""
        try:
            # Obtener certificado público
            public_crt = certificate.pem_certificate
            cert = x509.load_pem_x509_certificate(
                base64.b64decode(public_crt), backend=default_backend()
            )

            # Obtener clave privada
            private_key_pem = certificate.private_key_id.pem_key
            key = serialization.load_pem_private_key(
                base64.b64decode(private_key_pem), None, backend=default_backend()
            )

            return cert, key

        except Exception as e:
            _logger.error("Error al cargar certificado/clave: %s", str(e))
            raise UserError(
                _("Error al cargar el certificado o clave privada: %s") % str(e)
            ) from e

    def _get_numbering_range_response_process(self, record, values):
        """
        Procesar respuesta de consulta de rangos de numeración DIAN.

        :param values: Diccionario con la respuesta XML convertida con xmltodict
        :return: Diccionario con create_date
        """
        try:
            # Extraer create_date del timestamp
            create_date = (
                values.get("s:Envelope", {})
                .get("s:Header", {})
                .get("o:Security", {})
                .get("u:Timestamp", {})
                .get("u:Created", False)
            )

            if create_date:
                create_date = datetime.fromisoformat(create_date).replace(tzinfo=None)
            else:
                create_date = fields.Datetime.now()

            # Buscar la respuesta de numeración
            envelope = values.get("s:Envelope", {})
            body = envelope.get("s:Body", {})
            response = body.get("GetNumberingRangeResponse", {})
            result = response.get("GetNumberingRangeResult", {})

            # Verificar código de operación
            operation_code = result.get("b:OperationCode")
            if operation_code != "100":
                operation_desc = result.get(
                    "b:OperationDescription", "Error desconocido"
                )
                _logger.warning("[ERROR] EDI - DIAN: %s", operation_desc)
                record.message_post(
                    body=Markup(f"""<p class='text-danger'>[ERROR] EDI - DIAN
                        <br/>{operation_desc}</p>"""),
                )
                return {"create_date": create_date}

            # Obtener lista de respuestas
            response_list = result.get("b:ResponseList", {})
            number_ranges = response_list.get("c:NumberRangeResponse", [])

            # Asegurar que sea una lista
            if not isinstance(number_ranges, list):
                number_ranges = [number_ranges]

            # Buscar coincidencia con la resolución del journal
            target_resolution = record.l10n_co_electronic_document_resolution
            if not target_resolution:
                _logger.info("No hay resolución configurada en el journal")
                record.message_post(
                    body=Markup(f"""<p class='text-danger'>[ERROR] EDI - DIAN
                        <br/>No hay resolución configurada en el diario
                        electrónico <b>{record.name}</b></p>"""),
                )
                return {"create_date": create_date}

            # Buscar coincidencia
            matching_range = None
            for range_item in number_ranges:
                if range_item.get("c:ResolutionNumber") == target_resolution:
                    matching_range = range_item
                    break

            if matching_range:
                # Actualizar campos del journal directamente
                record.write(
                    {
                        "l10n_co_electronic_document_prefix": matching_range.get(
                            "c:Prefix"
                        ),
                        "l10n_co_electronic_document_start_number": int(
                            matching_range.get("c:FromNumber", 0)
                        ),
                        "l10n_co_electronic_document_end_number": int(
                            matching_range.get("c:ToNumber", 0)
                        ),
                        "l10n_co_dian_software_technical_key": (
                            matching_range.get("c:TechnicalKey")
                        ),
                        "l10n_co_electronic_document_start_resolution_date": (
                            matching_range.get("c:ValidDateFrom")
                        ),
                        "l10n_co_electronic_document_end_resolution_date": (
                            matching_range.get("c:ValidDateTo")
                        ),
                        "l10n_co_electronic_document_message": f"""Resolución \
de Facturación Nº \
{matching_range.get('c:ResolutionNumber')}, \
fecha {matching_range.get('c:ValidDateFrom')} a \
{matching_range.get('c:ValidDateTo')}, Prefijo \
{matching_range.get('c:Prefix')}, numeración desde \
{matching_range.get('c:FromNumber')} Hasta \
{matching_range.get('c:ToNumber')}""",
                    }
                )

                _logger.info(
                    "Resolución %s procesada para journal %s",
                    matching_range.get("c:ResolutionNumber"),
                    record.name,
                )
                record.message_post(
                    body=Markup(
                        f"""<p class='text-success'>[SUCCESS] EDI - DIAN\
                            <br/>{record.l10n_co_electronic_document_message} \
                            <b>procesada exitosamente desde DIAN</b></p>"""
                    ),
                )
            else:
                # No se encontró coincidencia
                available_resolutions = [
                    item.get("c:ResolutionNumber")
                    for item in number_ranges
                    if item.get("c:ResolutionNumber")
                ]

                _logger.info(
                    "No se encontró coincidencia para resolución %s. Disponibles: %s",
                    target_resolution,
                    available_resolutions,
                )
                record.message_post(
                    body=Markup(f"""<p>[WARNING] EDI - DIAN<br/>No se \
                        encontró coincidencia para resolución \
                        <b>{target_resolution}</b>. Disponibles: \
                        <b>{available_resolutions}</b></p>"""),
                )
            return {"create_date": create_date}

        except Exception as e:
            _logger.error("Error al procesar respuesta DIAN: %s", str(e))
            record.message_post(
                body=Markup(f"""<p>[ERROR] EDI - DIAN<br/>Error al \
                    procesar respuesta. <b>{str(e)}</b></p>"""),
            )
            return {"create_date": fields.Datetime.now()}

    def _export_invoice_constraints_new(self, invoice, vals):
        constraints = super()._export_invoice_constraints(invoice, vals)
        return constraints

    def _add_invoice_header_nodes(self, document_node, vals):
        super()._add_invoice_header_nodes(document_node, vals)
        invoice = vals["invoice"]
        start_date, end_date = invoice.journal_id._get_electronic_document_dates()
        document_node.update(
            {
                "xsi:schemaLocation": SCHEMES[vals["document_type"]],
                "cbc:UBLVersionID": {"_text": "UBL 2.1"},
                "cbc:CustomizationID": {
                    "_text": invoice._l10n_co_electronic_document_customization_id()
                },
                "cbc:ProfileID": {
                    "_text": PROFILE_ID[invoice.l10n_latam_document_type_id.code]
                },
                "cbc:ProfileExecutionID": {
                    "_text": "2"
                    if invoice.journal_id.l10n_co_dian_operation_mode == "test"
                    else "1"
                },
                "cbc:UUID": {
                    "schemeID": "2"
                    if invoice.journal_id.l10n_co_dian_operation_mode == "test"
                    else "1",
                    "schemeName": UUID_SCHEME_NAME[
                        invoice.l10n_latam_document_type_id.code
                    ],
                },
                "cbc:IssueDate": {
                    "_text": invoice.l10n_co_dian_generation_date.astimezone(
                        pytz.timezone("America/Bogota")
                    )
                    .date()
                    .isoformat()
                },
                "cbc:IssueTime": {
                    "_text": invoice.l10n_co_dian_generation_date.astimezone(
                        pytz.timezone("America/Bogota")
                    )
                    .isoformat(timespec="seconds")
                    .split("T")[1]
                },
                "cbc:InvoiceTypeCode": {
                    "_text": invoice.l10n_latam_document_type_id.code
                }
                if vals["document_type"] == "invoice"
                else None,
                "cbc:CreditNoteTypeCode": {
                    "_text": invoice.l10n_latam_document_type_id.code
                }
                if vals["document_type"] == "credit_note"
                else None,
                "cbc:Note": None,
                "cbc:DocumentCurrencyCode": {
                    "_text": "COP",
                    "listAgencyID": "6",
                    "listAgencyName": "United Nations Economic Commission for Europe",
                    "listID": "ISO 4217 Alpha",
                },
                "cbc:LineCountNumeric": {
                    "_text": len(
                        [
                            base_line
                            for base_line in vals["base_lines"]
                            if not base_line["special_mode"]
                        ]
                    )
                },
                "cac:InvoicePeriod": {
                    "cbc:StartDate": {"_text": start_date.isoformat()},
                    "cbc:EndDate": {"_text": end_date.isoformat()},
                }
                if invoice.l10n_latam_document_type_id.code in ["01", "02", "03"]
                else None,
                "cac:DiscrepancyResponse": (
                    {
                        "cbc:ReferenceID": {"_text": invoice.reversed_entry_id.name},
                        "cbc:ResponseCode": {"_text": "no definodo"},
                        "cbc:Description": {"_text": "no definido"},
                    }
                    if invoice.l10n_latam_document_type_id.code == "01"
                    or invoice.move_type == "in_refund"
                    else {
                        "cbc:ReferenceID": {"_text": invoice.debit_origin_id.name},
                        "cbc:ResponseCode": {"_text": "no definido"},
                        "cbc:Description": {"_text": "no definido"},
                    }
                    if invoice.l10n_latam_document_type_id.code == "03"
                    else None
                ),
            }
        )

        document_node["cac:OrderReference"]["cbc:SalesOrderID"] = None
        document_node["cac:BillingReference"] = "no definido"

        document_node.update(
            {
                "cac:PrepaidPayment": [
                    {
                        "cbc:ID": {"_text": p["name"]},
                        "cbc:PaidAmount": {
                            "_text": self.format_float(
                                p["amount"], invoice.company_currency_id.decimal_places
                            ),
                            "currencyID": invoice.company_currency_id.name,
                        },
                        "cbc:ReceivedDate": {"_text": p["date"]},
                    }
                    for p in vals["prepayments"]
                ]
                if vals["document_type"] in {"invoice", "credit_note"}
                else None,
            }
        )
        return

    def _add_invoice_config_vals(self, vals):
        super()._add_invoice_config_vals(vals)
        invoice = vals["invoice"]
        # prepayments = invoice._l10n_co_dian_get_invoice_prepayments()

        vals.update(
            {
                "document_type": "debit_note"
                if invoice.debit_origin_id
                else "credit_note"
                if invoice.move_type in ("out_refund", "in_refund")
                else "invoice",
                "algorithm": UUID_SCHEME_NAME[invoice.l10n_latam_document_type_id.code],
                "prepayments": [],
                "use_company_currency": True,
                "fixed_taxes_as_allowance_charges": False,
            }
        )
        return

    def _add_invoice_base_lines_vals(self, vals):
        super()._add_invoice_base_lines_vals(vals)
        for base_line in vals["base_lines"]:
            self._transform_iva_withholding_base_amount(base_line)
        return

    def _transform_iva_withholding_base_amount(self, base_line):
        def get_tax_data(tax_code):
            return next(
                (
                    tax_data
                    for tax_data in base_line["tax_details"]["taxes_data"]
                    if tax_data["tax"].l10n_co_tax_type_id.code == tax_code
                ),
                None,
            )

        tax_data_05 = get_tax_data("05")
        if tax_data_05:
            tax_data_01 = get_tax_data("01")
            tax_data_05["base_amount"] = (
                tax_data_01["tax_amount"] if tax_data_01 else 0.0
            )
        return

    def _add_invoice_tax_grouping_function_vals(self, vals):
        invoice = vals["invoice"]
        is_support_document = invoice.journal_id._is_support_document_type()
        self._add_document_tax_grouping_function_vals(vals)
        total_grouping_function = vals["total_grouping_function"]
        tax_grouping_function = vals["tax_grouping_function"]

        def total_grouping_function_excluding_support_document(base_line, tax_data):
            tax = tax_data and tax_data["tax"]
            if (
                is_support_document
                and tax
                and tax.l10n_co_tax_type_id.code not in {"01", "05", "06"}
            ):
                return None
            return total_grouping_function(base_line, tax_data)

        def tax_grouping_function_excluding_support_document(base_line, tax_data):
            tax = tax_data and tax_data["tax"]
            if (
                is_support_document
                and tax
                and tax.l10n_co_tax_type_id.code not in {"01", "05", "06"}
            ):
                return None
            return tax_grouping_function(base_line, tax_data)

        vals["total_grouping_function"] = (
            total_grouping_function_excluding_support_document
        )
        vals["tax_grouping_function"] = tax_grouping_function_excluding_support_document
        return

    def _add_document_tax_grouping_function_vals(self, vals):
        def total_grouping_function(base_line, tax_data):
            if tax_data and tax_data["tax"].l10n_co_tax_type_id.is_withholding_tax:
                return None
            return True

        def tax_grouping_function(base_line, tax_data):
            tax = tax_data and tax_data["tax"]
            if not tax:
                return None

            if tax.l10n_co_tax_type_id.code == "32":
                amount = (
                    tax.amount
                    / base_line["product_id"].l10n_co_edi_ref_nominal_tax
                    * base_line["quantity"]
                )
            elif tax.l10n_co_tax_type_id.code == "34":
                amount = (
                    tax.amount
                    * 100
                    / base_line["product_id"].l10n_co_edi_ref_nominal_tax
                )
            elif tax.l10n_co_tax_type_id.code == "05":
                if iva_tax := next(
                    (
                        tax_data["tax"]
                        for tax_data in base_line["tax_details"]["taxes_data"]
                        if tax_data["tax"].l10n_co_tax_type_id.code == "01"
                    ),
                    None,
                ):
                    amount = tax.amount * 100 / iva_tax.amount
            else:
                amount = tax.amount

            return {
                "l10n_co_tax_type_id": tax.l10n_co_tax_type_id,
                "amount_type": tax.amount_type,
                "amount": amount,
                "is_withholding_tax": tax.l10n_co_tax_type_id.is_withholding_tax,
            }

        vals["total_grouping_function"] = total_grouping_function
        vals["tax_grouping_function"] = tax_grouping_function
        return

    def _get_cufe_cude_cuds(self, document_node, vals):
        invoice = vals["invoice"]
        is_support_document = invoice.journal_id._is_support_document_type()

        def format_float(amount, precision_digits=vals["currency_dp"]):
            return self.format_float(amount, precision_digits)

        def get_tax_amount(tax_code):
            def grouping_function(base_line, tax_data):
                return tax_data and tax_data["tax"].l10n_co_tax_type_id.code == tax_code

            base_lines_aggregated_tax_details = self.env[
                "account.tax"
            ]._aggregate_base_lines_tax_details(vals["base_lines"], grouping_function)
            aggregated_tax_details = self.env[
                "account.tax"
            ]._aggregate_base_lines_aggregated_values(base_lines_aggregated_tax_details)
            if True in aggregated_tax_details:
                return aggregated_tax_details[True]["tax_amount"]
            return 0.0

        if invoice.l10n_latam_document_type_id.code in ("20", "30"):
            key = invoice.journal_id.l10n_co_dian_software_pin
        else:
            key = invoice.journal_id.l10n_co_dian_software_technical_key

        monetary_total_tag = (
            "cac:LegalMonetaryTotal"
            if vals["document_type"] in {"invoice", "credit_note"}
            else "cac:RequestedMonetaryTotal"
        )
        supplier_vat, supplier_verification_code = vals[
            "supplier"
        ]._l10n_co_get_vat_splited()
        customer_vat, customer_verification_code = vals[
            "customer"
        ]._l10n_co_get_vat_splited()

        cufe_cude_cuds_vals = {
            "invoice_id": document_node["cbc:ID"]["_text"],
            "issue_date": document_node["cbc:IssueDate"]["_text"],
            "issue_time": document_node["cbc:IssueTime"][
                "_text"
            ],  # invoice time (including tz)
            "line_extension_amount": document_node[monetary_total_tag][
                "cbc:LineExtensionAmount"
            ]["_text"],
            "tax_code_01": "01",
            "ValImp1": format_float(get_tax_amount("01")),
            "tax_code_04": "04",
            "ValImp2": format_float(get_tax_amount("04")),
            "tax_code_03": "03",
            "ValImp3": format_float(get_tax_amount("03")),
            "ValTotFac": document_node[monetary_total_tag]["cbc:PayableAmount"][
                "_text"
            ],
            "supplier_company_id": supplier_vat,
            "customer_company_id": customer_vat,
            "key": key or "missing_key",
            "profile_execution_id": document_node["cbc:ProfileExecutionID"]["_text"],
        }
        if is_support_document:
            [
                cufe_cude_cuds_vals.pop(k)
                for k in ("tax_code_04", "ValImp2", "tax_code_03", "ValImp3")
            ]

        return "".join(str(res) for res in cufe_cude_cuds_vals.values())

    def _get_invoice_node(self, vals):
        document_node = super()._get_invoice_node(vals)
        self._fill_cufe_cude_cuds(document_node, vals)
        return document_node

    def _add_invoice_accounting_supplier_party_nodes(self, document_node, vals):
        super()._add_invoice_accounting_supplier_party_nodes(document_node, vals)
        partner = vals["supplier"]
        document_node["cac:AccountingSupplierParty"]["cbc:AdditionalAccountID"] = {
            "_text": "1" if partner.is_company else "2"
        }
        return

    def _add_invoice_accounting_customer_party_nodes(self, document_node, vals):
        super()._add_invoice_accounting_customer_party_nodes(document_node, vals)
        partner = vals["customer"]
        document_node["cac:AccountingCustomerParty"]["cbc:AdditionalAccountID"] = {
            "_text": "1" if partner.is_company else "2"
        }
        return

    def _add_invoice_payment_means_nodes(self, document_node, vals):
        invoice = vals["invoice"]
        document_node["cac:PaymentMeans"] = {
            "cbc:ID": {"_text": invoice.l10n_co_payment_term},
            "cbc:PaymentMeansCode": {"_text": invoice.l10n_co_payment_method_id.code},
            "cbc:PaymentDueDate": {"_text": invoice.invoice_date_due},
            "cbc:PaymentID": {"_text": invoice.payment_reference or invoice.name},
        }
        return

    def _fill_cufe_cude_cuds(self, document_node, vals):
        invoice = vals["invoice"]
        cufe_cude_cuds = self._get_cufe_cude_cuds(document_node, vals)
        document_node["cbc:UUID"]["_text"] = sha384(
            cufe_cude_cuds.encode()
        ).hexdigest()  # as stated in the "Anexo Tecnico" file, SHA384 must be used
        document_node["cbc:Note"] = [
            document_node["cbc:Note"],
            {"_text": cufe_cude_cuds},
        ]

        if invoice.currency_id.name != "COP":
            document_node["cac:PaymentExchangeRate"] = {
                "cbc:SourceCurrencyCode": {"_text": "COP"},
                "cbc:SourceCurrencyBaseRate": {
                    "_text": (
                        rate := self.format_float(1 / invoice.invoice_currency_rate, 6)
                    )
                },
                "cbc:TargetCurrencyCode": {"_text": invoice.currency_id.name},
                "cbc:TargetCurrencyBaseRate": {"_text": "1.00"},
                "cbc:CalculationRate": {"_text": rate},
                "cbc:Date": {"_text": invoice.invoice_date},
            }
        return

    def _get_address_node(self, vals):
        partner = vals["partner"]
        return {
            "cbc:ID": {
                "_text": str(partner.city_id.zipcode).zfill(5)
            },  # Codigo Municipio
            "cbc:CityName": {"_text": partner.city},
            "cbc:PostalZone": {"_text": partner.zip},
            "cbc:CountrySubentity": {"_text": partner.state_id.name},
            "cbc:CountrySubentityCode": {"_text": str(partner.state_id.code).zfill(2)},
            "cac:AddressLine": {
                "cbc:Line": {
                    "_text": f"{partner.street or ''} {partner.street2 or ''}".strip()
                }
            },
            "cac:Country": {
                "cbc:IdentificationCode": {"_text": partner.country_id.code},
                "cbc:Name": {
                    "_text": partner.country_id.name,
                    "languageID": "es" if partner.country_code == "CO" else "en",
                },
            },
        }

    def _get_party_node(self, vals):
        partner = vals["partner"]
        invoice = vals["invoice"]
        role = vals["role"]
        commercial_partner = partner.commercial_partner_id
        vat, verification_code = commercial_partner._l10n_co_get_vat_splited()

        return {
            "cbc:IndustryClassificationCode": {
                "_text": invoice.company_id.l10n_co_ciiu_id.code
            }
            if role == "supplier" and invoice.l10n_latam_document_type_id.code != "95"
            else None,
            "cac:PartyIdentification": {
                "cbc:ID": {
                    "_text": vat,
                    "schemeName": (
                        commercial_partner.l10n_latam_identification_type_id.l10n_co_document_code
                    ),
                    "schemeID": verification_code,
                }
            }
            if not commercial_partner.is_company
            else None,
            "cac:PartyName": {"cbc:Name": {"_text": partner.display_name}},
            "cac:PhysicalLocation": {
                "cac:Address": self._get_address_node({"partner": partner})
            }
            if partner.vat != BUYER_NOT_IDENTIFIED_VAT
            else None,
            "cac:PartyTaxScheme": {
                "cbc:RegistrationName": {"_text": commercial_partner.name},
                "cbc:CompanyID": {
                    "_text": vat,
                    "schemeName": (
                        commercial_partner.l10n_latam_identification_type_id.l10n_co_document_code
                    ),
                    "schemeAgencyName": "CO, DIAN (Dirección de Impuestos \
y Aduanas Nacionales)",
                    "schemeAgencyID": "195",
                    "schemeID": verification_code if verification_code else None,
                },
                "cbc:TaxLevelCode": {
                    "_text": ";".join(
                        commercial_partner.l10n_co_responsibility_ids.mapped("code")
                    )
                },
                "cac:RegistrationAddress": self._get_address_node(
                    {"partner": commercial_partner}
                )
                if commercial_partner.vat != BUYER_NOT_IDENTIFIED_VAT
                else None,
                "cac:TaxScheme": {
                    "cbc:ID": {"_text": commercial_partner.l10n_co_regimen_fiscal},
                    "cbc:Name": {
                        "_text": dict(
                            commercial_partner._fields[
                                "l10n_co_regimen_fiscal"
                            ].selection
                        ).get(commercial_partner.l10n_co_regimen_fiscal)
                    },
                },
            },
            "cac:PartyLegalEntity": {
                "cbc:RegistrationName": {"_text": commercial_partner.name},
                "cbc:CompanyID": {
                    "_text": vat,
                    "schemeName": (
                        commercial_partner.l10n_latam_identification_type_id.l10n_co_document_code
                    ),
                    "schemeAgencyName": "CO, DIAN (Dirección de Impuestos \
y Aduanas Nacionales)",
                    "schemeAgencyID": "195",
                    "schemeID": verification_code if verification_code else None,
                },
            }
            if partner.vat != BUYER_NOT_IDENTIFIED_VAT
            else None,
            "cac:Contact": {
                "cbc:Name": {"_text": partner.name},
                "cbc:Telephone": {"_text": partner.phone},
                "cbc:ElectronicMail": {"_text": partner.email},
            }
            if partner.vat != BUYER_NOT_IDENTIFIED_VAT
            else None,
        }

    def _get_billing_reference_node(self, invoice):
        """Get the BillingReference node for credit/debit notes."""
        reference_invoice = None
        if (
            invoice.l10n_co_latam_document_type_id.code == "20"
            or invoice.move_type == "in_refund"
        ):
            reference_invoice = invoice.reversed_entry_id
            scheme_name = "CUDS" if invoice.move_type == "in_refund" else "CUFE"
        elif invoice.l10n_co_latam_document_type_id.code == "30":
            reference_invoice = invoice.debit_origin_id
            scheme_name = "CUFE"

        if reference_invoice:
            return {
                "cac:InvoiceDocumentReference": {
                    "cbc:ID": {"_text": reference_invoice.name},
                    "cbc:UUID": {
                        "_text": reference_invoice.l10n_co_edi_cufe_cude_ref,
                        "schemeName": f"{scheme_name}-SHA384",
                    },
                    "cbc:IssueDate": {
                        "_text": reference_invoice.invoice_date.isoformat()
                    },
                }
            }
        return None

    def _add_document_tax_total_nodes(self, document_node, vals):
        base_lines_aggregated_tax_details = {}
        aggregated_tax_details = {}
        base_unit_measure_by_grouping_key = defaultdict(float)

        def grouping_function(base_line, tax_data):
            grouping_key = vals["tax_grouping_function"](base_line, tax_data)
            if grouping_key is not None and tax_data[
                "tax"
            ].l10n_co_tax_type_id.code in ["32", "34"]:
                base_unit_measure_by_grouping_key[frozendict(grouping_key)] += (
                    base_line["product_id"].l10n_co_edi_ref_nominal_tax
                    * (
                        base_line["quantity"]
                        if tax_data["tax"].l10n_co_tax_type_id.code == "34"
                        else 1
                    )
                )
            return grouping_key

        base_lines_aggregated_tax_details = self.env[
            "account.tax"
        ]._aggregate_base_lines_tax_details(
            vals["base_lines"],
            grouping_function,
        )
        aggregated_tax_details = self.env[
            "account.tax"
        ]._aggregate_base_lines_aggregated_values(
            base_lines_aggregated_tax_details,
        )

        grouped_aggregated_tax_details_by_tax_type = {
            "tax": defaultdict(dict),
            "withholding_tax": defaultdict(dict),
        }

        for grouping_key, values in aggregated_tax_details.items():
            if grouping_key:
                l10n_co_tax_type_id = grouping_key["l10n_co_tax_type_id"]
                key = "withholding_tax" if grouping_key["is_withholding_tax"] else "tax"
                grouped_aggregated_tax_details_by_tax_type[key][l10n_co_tax_type_id][
                    grouping_key
                ] = values
                values["base_unit_measure"] = base_unit_measure_by_grouping_key[
                    grouping_key
                ]

        document_node["cac:TaxTotal"] = [
            self._get_tax_total_node(
                {**vals, "aggregated_tax_details": tax_details, "role": "document"}
            )
            for tax_details in grouped_aggregated_tax_details_by_tax_type[
                "tax"
            ].values()
        ]
        if vals["document_type"] == "invoice":
            document_node["cac:WithholdingTaxTotal"] = [
                self._get_tax_total_node(
                    {
                        **vals,
                        "aggregated_tax_details": tax_details,
                        "role": "document",
                        "sign": -1,
                    }
                )
                for tax_details in grouped_aggregated_tax_details_by_tax_type[
                    "withholding_tax"
                ].values()
            ]

    def _add_invoice_monetary_total_nodes(self, document_node, vals):
        super()._add_invoice_monetary_total_nodes(document_node, vals)
        prepaid_amount = sum(p["amount"] for p in vals["prepayments"])
        monetary_total_tag = self._get_tags_for_document_type(vals)["monetary_total"]
        document_node[monetary_total_tag].update(
            {
                "cbc:PrepaidAmount": {
                    "_text": self.format_float(prepaid_amount, vals["currency_dp"]),
                    "currencyID": vals["currency_name"],
                }
                if prepaid_amount
                else None,
                "cbc:PayableAmount": {
                    "_text": document_node[monetary_total_tag][
                        "cbc:TaxInclusiveAmount"
                    ]["_text"],
                    "currencyID": vals["currency_name"],
                },
            }
        )
        return

    def _get_tax_subtotal_node(self, vals):
        tax_details = vals["tax_details"]
        grouping_key = vals["grouping_key"]

        if grouping_key["l10n_co_tax_type_id"].code not in ["32", "34"]:
            tax_subtotal_node = super()._get_tax_subtotal_node(vals)
            tax_subtotal_node["cbc:Percent"] = None
        else:
            tax_subtotal_node = {
                "cbc:TaxAmount": {
                    "_text": self.format_float(
                        tax_details["tax_amount"], vals["currency_dp"]
                    ),
                    "currencyID": vals["currency_name"],
                },
                "cbc:BaseUnitMeasure": {
                    "_text": tax_details["base_unit_measure"],
                    "unitCode": "LTR"
                    if grouping_key["l10n_co_tax_type_id"].code == "32"
                    else "ML",
                },
                "cbc:PerUnitAmount": {
                    "_text": self.format_float(grouping_key["amount"], 2),
                    "currencyID": vals["currency_name"],
                },
                "cac:TaxCategory": self._get_tax_category_node(vals),
            }

        return tax_subtotal_node

    def _get_tax_category_node(self, vals):
        grouping_key = vals["grouping_key"]
        return {
            "cbc:Percent": {
                "_text": FloatFmt(
                    abs(grouping_key["amount"]), 2, 3
                )  # withholding taxes are reported as positives
            }
            if grouping_key["l10n_co_tax_type_id"].code not in {"32", "34"}
            else None,  # Don't include Percent for ICL/IBUA taxes
            "cac:TaxScheme": {
                "cbc:ID": {
                    "_text": grouping_key["l10n_co_tax_type_id"].code,
                },
                "cbc:Name": {
                    "_text": "No aplica"
                    if grouping_key["l10n_co_tax_type_id"].name == "No Aplica"
                    else grouping_key["l10n_co_tax_type_id"].name
                },
            },
        }

    def _add_document_line_amount_nodes(self, line_node, vals):
        super()._add_document_line_amount_nodes(line_node, vals)
        base_line = vals["base_line"]
        uom = base_line["product_uom_id"].unece_code_id.code or "94"
        quantity_tag = self._get_tags_for_document_type(vals)["line_quantity"]
        line_node[quantity_tag]["unitCode"] = uom
        return

    def _add_invoice_line_note_nodes(self, line_node, vals):
        invoice = vals["invoice"]
        base_line = vals["base_line"]
        if invoice.l10n_latam_document_type_id.code == "09" and base_line["product_id"]:
            line_node["cbc:Note"] = {
                "_text": f"Contrato de servicios AIU por \
Concepto de: {base_line['product_id'].name}"
            }
        return

    def _add_invoice_line_period_nodes(self, line_node, vals):
        super()._add_invoice_line_period_nodes(line_node, vals)
        line = vals["base_line"]["record"]
        invoice = vals["invoice"]
        is_support_document = invoice.journal_id._is_support_document_type()
        if is_support_document:
            line_node["cac:InvoicePeriod"] = {
                "cbc:StartDate": {"_text": line.move_id.invoice_date},
                "cbc:DescriptionCode": {"_text": 1},
                "cbc:Description": {"_text": "Por operación"},
            }
        return

    def _add_document_line_tax_total_nodes(self, line_node, vals):
        base_unit_measure_by_grouping_key = defaultdict(float)

        def grouping_function(base_line, tax_data):
            grouping_key = vals["tax_grouping_function"](base_line, tax_data)
            if grouping_key is not None and tax_data[
                "tax"
            ].l10n_co_tax_type_id.code in ["32", "34"]:
                base_unit_measure_by_grouping_key[frozendict(grouping_key)] += (
                    base_line["product_id"].l10n_co_edi_ref_nominal_tax
                    * (
                        base_line["quantity"]
                        if tax_data["tax"].l10n_co_tax_type_id.code == "34"
                        else 1
                    )
                )
            return grouping_key

        aggregated_tax_details = self.env[
            "account.tax"
        ]._aggregate_base_line_tax_details(
            vals["base_line"],
            grouping_function,
        )

        grouped_aggregated_tax_details_by_tax_type = {
            "tax": defaultdict(dict),
            "withholding_tax": defaultdict(dict),
        }

        for grouping_key, values in aggregated_tax_details.items():
            if grouping_key:
                l10n_co_tax_type_id = grouping_key["l10n_co_tax_type_id"]
                key = "withholding_tax" if grouping_key["is_withholding_tax"] else "tax"
                grouped_aggregated_tax_details_by_tax_type[key][l10n_co_tax_type_id][
                    grouping_key
                ] = values
                values["base_unit_measure"] = base_unit_measure_by_grouping_key[
                    grouping_key
                ]

        line_node["cac:TaxTotal"] = [
            self._get_tax_total_node(
                {**vals, "aggregated_tax_details": tax_details, "role": "line"}
            )
            for tax_details in grouped_aggregated_tax_details_by_tax_type[
                "tax"
            ].values()
        ]
        if vals["document_type"] == "invoice":
            line_node["cac:WithholdingTaxTotal"] = [
                self._get_tax_total_node(
                    {
                        **vals,
                        "aggregated_tax_details": tax_details,
                        "role": "line",
                        "sign": -1,
                    }
                )
                for tax_details in grouped_aggregated_tax_details_by_tax_type[
                    "withholding_tax"
                ].values()
            ]
        return

    def _add_invoice_line_item_nodes(self, line_node, vals):
        super()._add_invoice_line_item_nodes(line_node, vals)
        base_line = vals["base_line"]
        line = base_line["record"]
        invoice = vals["invoice"]
        is_support_document = invoice.journal_id._is_support_document_type()
        product = base_line["product_id"]
        if line.move_id.l10n_latam_document_type_id.code == "30":
            line_node["cac:Item"]["cbc:BrandName"] = {"_text": product.product_brand}
            line_node["cac:Item"]["cbc:ModelName"] = {"_text": product.product_model}

        line_node["cac:Item"]["cac:SellersItemIdentification"] = {
            "cbc:ID": {"_text": product.default_code},
            "cbc:ExtendedID": {"_text": product.default_code}
            if is_support_document
            else None,
        }
        line_node["cac:Item"]["cac:StandardItemIdentification"] = {
            "cbc:ID": {
                "_text": product.barcode,
                "schemeID": "0160",
                "schemeName": "GTIN",
            }
        }
        return

    def _get_line_discount_allowance_charge_node(self, vals):
        discount_node = super()._get_line_discount_allowance_charge_node(vals)
        if discount_node:
            discount_node["cbc:AllowanceChargeReasonCode"] = {
                "_text": "00"
            }  # unconditional discount
            discount_node["cbc:MultiplierFactorNumeric"] = {
                "_text": vals["base_line"]["discount"]
            }
            discount_node["cbc:BaseAmount"] = {
                "_text": self.format_float(vals["gross_subtotal"], vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            }
        return discount_node

    def _add_document_line_price_nodes(self, line_node, vals):
        super()._add_document_line_price_nodes(line_node, vals)
        base_line = vals["base_line"]
        uom = base_line["product_uom_id"].unece_code_id.code or "94"
        line_node["cac:Price"]["cbc:BaseQuantity"] = {
            "_text": base_line["quantity"],
            "unitCode": uom,
        }
        return

    def _get_document_nsmap(self, vals):
        nsmap = super()._get_document_nsmap(vals)
        nsmap.update(
            {
                "ds": "http://www.w3.org/2000/09/xmldsig#",
                "sts": "dian:gov:co:facturaelectronica:Structures-2-1"
                if vals["document_type"] == "invoice"
                else "http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures",
                "xades": "http://uri.etsi.org/01903/v1.3.2#",
                "xades141": "http://uri.etsi.org/01903/v1.4.1#",
                "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            }
        )
        return nsmap

    def _fill_dian_data(self, xml_content, record):
        """Rellenar datos de la factura para el envío a DIAN."""
        return xml_content
