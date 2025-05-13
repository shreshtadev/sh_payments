// Copyright (c) 2025, shreshtadev and contributors
// For license information, please see license.txt

frappe.ui.form.on("ShPayment", {
    refresh(frm) {
        if (frm.from_to === null) {
            frm.add_custom_button("Create Customer", () => {
                frappe.new_doc("ShCustomer", {
                    customer_type: frm.doc.payment_type,
                });
            });
        }
    },
});
