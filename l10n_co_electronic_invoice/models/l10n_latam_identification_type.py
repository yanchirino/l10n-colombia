from odoo import fields, models


class L10nLatamIdentificationType(models.Model):
    _inherit = "l10n_latam.identification.type"

    l10n_co_document_iso_code = fields.Char(string="ISO Code")
