from odoo import fields, models


class WebserviceBackend(models.Model):
    _inherit = "webservice.backend"

    content_type = fields.Selection(
        selection_add=[
            ("application/soap+xml", "SOAP+XML"),
        ],
    )
