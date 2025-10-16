from odoo import fields, models


class EDIExchangeType(models.Model):
    _inherit = "edi.exchange.type"

    l10n_co_dian_webservice_action = fields.Char(
        string="Acción del Webservice de la DIAN",
        help="""Acción del Webservice de la DIAN a la que se \
enviará el mensaje.""",
    )
    l10n_co_dian_document_requires_signature = fields.Boolean(
        string="Requiere firma electrónica del documento",
        help="""Indica si el documento requiere ser firmado \
electrónicamente para ser enviado a la DIAN.""",
    )
    l10n_co_dian_body_zipped = fields.Boolean(
        string="Body zipped",
        help="Indica si el body del SOAP Envelope debe ser zipped.",
    )
