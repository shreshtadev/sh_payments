import csv
import logging
import os
import re
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
    uoms = ["pcs", "pkt", "set", "box", "unit"]
    item_code_lower = item_code.lower()

    # First check for PCS,PKT,SET,BOX,UNIT if SHEET is also present
    for uom in uoms:
        if (
            uom in item_code_lower
            and re.search(r"\d+\s*sheets?", item_code_lower) is not None
        ):
            return frappe.get_doc("UOM", "pkt")

    # Then check other keywords
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
            existing_item = frappe.get_doc("Item", product_name)
            existing_item_tax = frappe.get_all(
                "Item Tax", fields=["name"], filters=[["parent", "=", product_name]]
            )
            if len(existing_item_tax) > 0:
                return
            # Update existing item if needed
            return
        except frappe.DoesNotExistError:
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


def get_company_details():
    """Get company details and validate."""
    try:
        company = frappe.get_doc("Company", "Shree Graphics")
        return {
            "company": company,
            "abbr": company.get("abbr"),
            "item_group_name": company.name,
        }
    except frappe.DoesNotExistError:
        logging.error("Company 'Shree Graphics' not found")
        raise
    except Exception as e:
        logging.error(f"Error getting company details: {e}")
        raise


def process_gst_rate(gst):
    """Process GST rate and return formatted strings."""
    gst = gst.replace(" ", "")
    gst_rate = f"GST {gst}"
    actual_gst_rate = gst.split("%")[0]
    return gst_rate if int(actual_gst_rate) != 0 else "Exempted"


def get_hsn_code(hsn_code_csv):
    """Get HSN code from database."""
    hsn_code_list = frappe.get_list(
        "GST HSN Code", filters={"hsn_code": ["like", f"%{hsn_code_csv}%"]}
    )
    if not hsn_code_list:
        logging.warning(f"HSN Code Not Found For {hsn_code_csv}")
        return None
    return hsn_code_list[0]


def process_single_product(product, company_abbr, item_group_name):
    """Process a single product entry."""
    product_name = product.get("product_name", "").strip()
    hsn_code_csv = product.get("hsn_code", "").strip()

    if not product_name or not hsn_code_csv:
        logging.warning(
            f"Skipping row due to missing product_name or hsn_code: {product}"
        )
        return False

    gst_rate_with_exempted = process_gst_rate(product.get("gst", ""))
    hsn_code = get_hsn_code(hsn_code_csv)

    if not hsn_code:
        logging.warning(f"Skipping {product_name} - HSN code {hsn_code_csv} not found")
        return False

    tax_template_name = f"{gst_rate_with_exempted} - {company_abbr}"
    stock_uom_name = str(find_stock_uom(product_name).name)

    try:
        create_products(
            product_name=product_name,
            tax_template_name=tax_template_name,
            stock_uom_name=stock_uom_name,
            hsn_code=hsn_code,
            item_group_name=item_group_name,
        )
        return True
    except Exception as e:
        logging.error(
            f"Error processing product {product_name}: {e}\n{traceback.format_exc()}"
        )
        return False


def execute():
    """Add Items from CSV to ERPNext."""
    file_path = os.path.join(os.path.dirname(__file__), "data", "sgproducts_1.csv")

    try:
        company_details = get_company_details()
        products = load_products(file_path=file_path)

        success_count = 0
        for product in products:
            if process_single_product(
                product, company_details["abbr"], company_details["item_group_name"]
            ):
                success_count += 1

        try:
            frappe.db.commit()
            logging.info(
                f"Successfully processed {success_count} out of {len(products)} products"
            )
        except Exception as e:
            logging.error(f"Database commit failed: {e}\n{traceback.format_exc()}")
            frappe.db.rollback()

    except Exception as e:
        logging.error(f"Unable to import items: {e}\n{traceback.format_exc()}")
        frappe.db.rollback()
