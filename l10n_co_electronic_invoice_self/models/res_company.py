from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _get_l10n_co_dian_self_params(self):
        self.ensure_one()
        return (
            self.l10n_co_regimen_fiscal,
            self.l10n_co_responsibility_ids,
            self.l10n_co_ciiu_id,
        )
