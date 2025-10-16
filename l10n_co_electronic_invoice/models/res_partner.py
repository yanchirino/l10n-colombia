# Copyright 2025 IKU Solutions - Yan Chirino <yan.chirino@iku.solutions>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_co_regimen_fiscal = fields.Selection(
        selection=[
            ("48", "Impuesto sobre las ventas – IVA"),
            ("49", "No responsable de IVA"),
        ],
        string="Regimen Fiscal",
    )
    l10n_co_responsibility_ids = fields.Many2many(
        "l10n_co.responsibility.type", string="Responsabilidades"
    )
    l10n_co_ciiu_id = fields.Many2one("l10n_co.ciiu", "Principal actividad economica")
    l10n_co_ciiu_ids = fields.Many2many(
        "l10n_co.ciiu", string="Otras actividades economicas"
    )

    def _l10n_co_get_vat_splited(self):
        self.ensure_one()
        if self.l10n_latam_identification_type_id.l10n_co_document_code != "07":
            return self.vat, None
        elif self.vat and "-" in self.vat:
            return self.vat.split("-")
        return self.vat[:-1], self.vat[-1] if self.vat else "", None
