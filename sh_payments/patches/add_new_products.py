import csv
import logging
import os
import traceback

import frappe

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
)


def find_tax_category(category_type):
    tx_cat = frappe.get_doc("Tax Category", category_type)
    return str(tx_cat.name)


def find_stock_uom(item_code: str):
    uom_keywords = {
        "pcs": "pcs",
        "sheet": "sheets",
        "pkt": "pkt",
        "set": "set",
        "box": "box",
        "unit": "unit",
    }
    item_code_lower = item_code.lower()
    for keyword, uom in uom_keywords.items():
        if keyword in item_code_lower:
            return frappe.get_doc("UOM", uom)
    return frappe.get_doc("UOM", "nos")


def load_products(file_path):
    """Reads a CSV file, treating each row as a dictionary."""
    file_fields = []
    with open(file_path, mode="r", newline="", encoding="utf-8") as file:
        csv_reader = csv.DictReader(file)

        print(f"Field Names: {csv_reader.fieldnames}")

        print("\nData Rows (as dictionaries):")

        for row in csv_reader:
            # Access data by column name
            file_fields.append(row)
    return file_fields


def create_products(
    product_name, tax_template_name, stock_uom_name, hsn_code, item_group_name
):
    if hsn_code:
        try:
            frappe.get_doc("Item", product_name)
        except Exception:
            item_to_save = frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": product_name,
                    "item_name": product_name,
                    "item_group": item_group_name,
                    "gst_hsn_code": hsn_code.name,
                    "taxes": [
                        {
                            "item_tax_template": tax_template_name,
                            "tax_category": find_tax_category("In-State"),
                            "minimum_net_rate": 0,
                            "maximum_net_rate": 0,
                        }
                    ],
                    "is_stock_item": False,
                    "stock_uom": stock_uom_name,
                }
            )
            item_to_save.save(ignore_permissions=True)
    else:
        logging.error(f"Invalid HSN CODE for {product_name}")


def execute():
    """Adding Items"""
    file_path = os.path.join(os.path.dirname(__file__), "data", "sgproducts.csv")

    company = frappe.get_doc("Company", "Shree Graphics")
    company_name = company.name if company is not None else ""
    company_abbr = company.get("abbr")
    item_group = (
        frappe.get_doc("Item Group", str(company_name)) if company is not None else None
    )
    item_group_name = item_group.name if item_group is not None else ""
    read_sgp_file = load_products(file_path=file_path)
    try:
        for sgpb in read_sgp_file:
            product_name = sgpb["product_name"].strip()
            gst_rate_str = sgpb["gst"]
            hsn_code_csv = sgpb["hsn_code"].strip()
            hsn_code = ""
            try:
                hsn_code = frappe.get_list(
                    "GST HSN Code", filters=[["hsn_code", "LIKE", f"%{hsn_code_csv}%"]]
                )[0]
            except Exception:
                logging.warning(f"HSN Code Not Found For {hsn_code_csv}")

            tax_template_name = f"GST {gst_rate_str} - {str(company_abbr)}"
            stock_uom_name = str(find_stock_uom(product_name).name)
            create_products(
                product_name=product_name,
                tax_template_name=tax_template_name,
                stock_uom_name=stock_uom_name,
                hsn_code=hsn_code,
                item_group_name=item_group_name,
            )
        frappe.db.commit()
    except Exception:
        logging.error(f"Unable to import items {traceback.print_exc()}")
        frappe.db.rollback()
