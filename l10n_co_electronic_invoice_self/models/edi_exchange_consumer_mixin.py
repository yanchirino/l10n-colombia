from odoo import models


class EDIExchangeConsumerMixin(models.AbstractModel):
    _inherit = "edi.exchange.consumer.mixin"

    def edi_create_exchange_record(self, exchange_type_id):
        result = super().edi_create_exchange_record(exchange_type_id)
        if (
            isinstance(result, dict)
            and result.get("res_model") == "edi.exchange.record"
        ):
            record = self.env[result.get("res_model")].browse(result.get("res_id"))
            if record.edi_exchange_state == "output_sent_and_processed":
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "type": "success",
                        "sticky": False,
                        "message": ("La operación ha sido completada."),
                        "next": {"type": "ir.actions.client", "tag": "soft_reload"},
                    },
                }
        return result
