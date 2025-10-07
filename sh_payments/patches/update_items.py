import logging
import os
import traceback

import frappe
import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def find_tax_category(category_type):
    tx_cat = frappe.get_doc("Tax Category", category_type)
    return str(tx_cat.name)


def generate_company_nabbr():
    company_abbrs = [
        (
            cmp["name"],
            cmp["abbr"],
        )
        for cmp in frappe.get_all("Company", fields=["name", "abbr"])
    ]
    return company_abbrs


def update_by_hsn():
    """Update Taxes By Item HSN Code"""
    filename = "pricelistupdates.csv"
    column_names = ["hsn_code", "updated_gst"]
    taxupdates_df = pd.read_csv(
        os.path.join(os.path.dirname(__file__), "data", filename),
        usecols=column_names,
        header=0,
    )
    frappe.msgprint("Reading Updated PriceList")
    tax_category = frappe.get_doc("Tax Category", "In-State")
    company_abbrs = [
        cmp["abbr"]
        for cmp in frappe.get_all(
            "Company",
            fields=["abbr"],
        )
    ]
    items = frappe.get_list("Item", fields=["name", "gst_hsn_code"])
    taxupdates_df["updated_gst_perc"] = (
        (taxupdates_df["updated_gst"] * 100).astype(int).astype(str)
    )
    tax_map = taxupdates_df.set_index("hsn_code")["updated_gst_perc"].to_dict()
    for item_data in items:
        item_name = item_data.name
        item_hsn = int(item_data.gst_hsn_code)
        if not item_hsn:
            continue
        if item_hsn in tax_map:
            gst_rate_str = tax_map[item_hsn]
            try:
                item_doc = frappe.get_doc("Item", item_name)
                tax_template_names = [
                    f"GST {gst_rate_str}% - {cabbr}"
                    if int(gst_rate_str) > 0
                    else f"Exempted - {cabbr}"
                    for cabbr in company_abbrs
                ]
                item_doc.set("taxes", [])
                for tax_template_name in tax_template_names:
                    item_tx = {
                        "item_tax_template": tax_template_name,
                        "tax_category": tax_category.name,
                        "minimum_net_rate": 0,
                        "maximum_net_rate": 0,
                    }
                    item_doc.append(
                        "taxes",
                        item_tx,
                    )
                item_doc.save()
                frappe.db.commit()

            except Exception:
                logging.error(
                    f"Error updating Item {item_name} (HSN {item_hsn}): {traceback.print_exc()}",
                )
                frappe.db.rollback()  # Rollback on error


def execute():
    update_by_hsn()
