from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _get_l10n_co_dian_self_params(self):
        params = []
        # Lineas con produtos, se excluyen las lineas contables
        sale_lines = self.filtered(lambda line: line.product_id)
        for line in sale_lines:
            params.append(line.tax_ids)
            params.append(line.product_uom_id.unece_code_id)
            params.append(line.product_id.product_tmpl_id.product_unspsc_id)
        return params
