// Copyright (c) 2025, shreshtadev and contributors
// For license information, please see license.txt

frappe.ui.form.on("ShCustomer", {
    refresh: function (frm) {
        frm.add_custom_button("Create Receipt", () => {
            if (frm.doc.name) {
                frappe.new_doc("ShPayment", {
                    payment_type: 'Receipt',
                    from_to: frm.doc.name,
                });
            }
        });
        frm.add_custom_button("Create Voucher", () => {
            if (frm.doc.name) {
                frappe.new_doc("ShPayment", {
                    payment_type: 'Voucher',
                    from_to: frm.doc.name,
                });
            }
        });
    },
});
