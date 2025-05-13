# Copyright (c) 2025, shreshtadev and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime
from frappe.model.document import Document


class ShPayment(Document):
    def validate(self):
        if not self.payment_date:
            self.payment_date = datetime.now()
        if not self.sl_no and not self.payment_type:
            frappe.throw("SlNo/Payment Type is mandatory")
        else:
            if not self.narration:
                is_credit_debit = 'Credited' if self.payment_type == 'Receipt' else 'Debited'
                self.narration = f'{self.from_to} has {is_credit_debit} ₹{self.total_amount} via {self.paid_on}'
