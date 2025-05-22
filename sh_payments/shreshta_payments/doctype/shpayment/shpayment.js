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


frappe.ui.form.on("ShBill", {
    quantity: function (frm, cdt, cdn) {
        updateRowTotal(cdt, cdn);
        updateTotal(frm);
    },
    price: function (frm, cdt, cdn) {
        updateRowTotal(cdt, cdn);
        updateTotal(frm);
    },
    cgst: function (frm, cdt, cdn) {
        updateRowTotal(cdt, cdn);
        updateTotal(frm);
    },
    sgst: function (frm, cdt, cdn) {
        updateRowTotal(cdt, cdn);
        updateTotal(frm);
    }
});

function updateRowTotal(cdt, cdn) {
    const row = locals[cdt][cdn];
    row.cgst = row.cgst || 0;
    row.sgst = row.sgst || 0;
    const grossAmount = row.price * row.quantity;
    const gstRate = (row.cgst + row.sgst) / 100;
    const netAmount = grossAmount + (grossAmount * gstRate);
    frappe.model.set_value(cdt, cdn, 'amount', flt(netAmount));
}

function updateTotal(frm) {
    let totalAmount = 0;

    frm.doc.table_jmgk.forEach(row => {
        const grossAmount = row.price * row.quantity;
        const gstRate = (row.cgst + row.sgst) / 100;
        const netAmount = grossAmount + (grossAmount * gstRate);
        totalAmount += netAmount;
    });
    frm.set_value('total_amount', flt(totalAmount));
}
