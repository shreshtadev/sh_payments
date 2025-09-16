from collections import defaultdict

import frappe


@frappe.whitelist()
def get_total_tax_summary(invoice_no):
    if not invoice_no:
        return {"status": "RequestError", "error": "Invoice Number is mandatory."}
    found_invoice = frappe.get_doc("Sales Invoice", invoice_no)
    if not found_invoice:
        return {"status": "NotFound", "error": "Invoice not found."}
    found_items = get_tax_summary(found_invoice)
    return found_items


def get_tax_summary(doc):
    summary = defaultdict(
        lambda: {
            "total_sgst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "cgst_rate": 0.0,
            "sgst_rate": 0.0,
            "gst_rate": 0.0,
            "total_gst_amount": 0.0,
            "net_amount": 0.0,
        }
    )

    for item in doc.items:
        cgst = item.cgst_amount or 0
        sgst = item.sgst_amount or 0
        net = item.net_amount or 0
        cgst_rate = item.cgst_rate or 0
        sgst_rate = item.sgst_rate or 0
        gst_rate = cgst_rate + sgst_rate

        summary[gst_rate]["total_cgst_amount"] += cgst
        summary[gst_rate]["total_sgst_amount"] += sgst
        summary[gst_rate]["total_gst_amount"] += cgst + sgst
        summary[gst_rate]["net_amount"] += net
        summary[gst_rate]["cgst_rate"] = cgst_rate
        summary[gst_rate]["sgst_rate"] = sgst_rate
        summary[gst_rate]["gst_rate"] = cgst_rate + sgst_rate

    item_summary = [
        {
            "cgst_rate": round(v["cgst_rate"], 1),
            "sgst_rate": round(v["sgst_rate"], 1),
            "gst_rate": round(v["gst_rate"], 1),
            "total_cgst_amount": round(v["total_cgst_amount"], 2),
            "total_sgst_amount": round(v["total_sgst_amount"], 2),
            "total_gst_amount": round(v["total_gst_amount"], 2),
            "net_amount": round(v["net_amount"], 2),
        }
        for k, v in summary.items()
    ]
    return item_summary
