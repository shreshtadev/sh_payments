import traceback

import frappe


def execute():
    invoices = frappe.get_all(
        "Sales Invoice", filters={"docstatus": ["<", 2]}, fields=["name"]
    )
    for inv in invoices:
        try:
            doc = frappe.get_doc("Sales Invoice", inv.name)
            summary = frappe.call(
                "sh_payments.api.tax_summary.get_total_tax_summary", invoice_no=doc.name
            )
            frappe.log("Made request to get Tax Summary")
            doc.set("si_tax_summary", [])  # type: ignore
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
            frappe.log("Updating tax summary")
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.log("Updated tax summary")
        except Exception as e:
            traceback_str = traceback.format_exc()
            frappe.log(
                f"Failed to backfill {inv.name}: {str(e)}\n\nTraceback:\n{traceback_str}"
            )
            frappe.db.rollback()
            raise Exception(
                f"Failed to backfill {inv.name}: {str(e)}\n\nTraceback:\n{traceback_str}"
            )
    frappe.log("Patch completed.")
