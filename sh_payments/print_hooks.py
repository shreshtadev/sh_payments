import frappe


def attach_tax_summary(doc, method=None):
    if doc.doctype != "Sales Invoice":
        return
    try:
        response = frappe.call(
            "sh_payments.api.tax_summary.get_total_tax_summary",
            invoice_no=doc.name,
        )
        doc.set("si_tax_summary", [])
        summary = response or []

        for row in summary:
            doc.append(
                "si_tax_summary",
                {
                    "total_gst_amount": row.get("total_gst_amount"),
                    "total_sgst_amount": row.get("total_cgst_amount"),
                    "total_cgst_amount": row.get("total_sgst_amount"),
                    "gst_rate": row.get("gst_rate"),
                    "sgst_rate": row.get("cgst_rate"),
                    "cgst_rate": row.get("sgst_rate"),
                    "net_amount": row.get("net_amount"),
                },
            )

    except Exception as e:
        frappe.log_error(
            f"Tax summary load failed: {str(e)}", "Sales Invoice Tax Summary"
        )
