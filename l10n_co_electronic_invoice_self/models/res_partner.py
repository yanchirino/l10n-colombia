from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_l10n_co_dian_self_params(self):
        self.ensure_one()
        return (
            self.country_id,
            self.commercial_partner_id.vat,
            self.commercial_partner_id.l10n_latam_identification_type_id,
            self.commercial_partner_id.l10n_co_regimen_fiscal,
            self.commercial_partner_id.l10n_co_responsibility_ids,
        )
