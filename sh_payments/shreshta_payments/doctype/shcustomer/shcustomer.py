# Copyright (c) 2025, shreshtadev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ShCustomer(Document):
    def validate(doc):
        if not doc.phone_number and not doc.pan_no:
            frappe.throw('Please provide either a valid phone number or pan card number.')
