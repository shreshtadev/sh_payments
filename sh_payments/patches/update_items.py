import json
import os
import re

import frappe
import pandas as pd


def is_similar(hsn_full: str, hsn_base: str) -> bool:
    # Ensure strings, pad with zeros if necessary
    hsn_full = hsn_full.zfill(
        len(hsn_full)
        + (len(hsn_base) - len(hsn_full) if len(hsn_base) > len(hsn_full) else 0)
    )
    return hsn_full.startswith(hsn_base)


def find_hsn_match(hsn_raw: str) -> str | None:
    """Find a matching 'GST HSN Code' doc name for the provided HSN string.

    Tries exact match first, then prefix matches, then shorter-prefix similarity checks.
    Returns the matching doc name (hsn code string) or None.
    """
    if not hsn_raw:
        return None
    # normalize to digits
    norm = re.sub(r"\D", "", str(hsn_raw))
    if not norm:
        return None

    # exact lookup (doctype autoname is hsn_code)
    try:
        if frappe.db.exists("GST HSN Code", norm):
            return norm
    except Exception:
        # table may not exist in some installs
        pass

    # try prefix matches (longer first)
    try:
        candidates = frappe.get_all(
            "GST HSN Code",
            filters=[["hsn_code", "like", f"{norm}%"]],
            fields=["hsn_code"],
            limit=10,
        )
        if candidates:
            # prefer exact prefix equal to norm, otherwise return first
            for c in candidates:
                if c.hsn_code == norm:
                    return c.hsn_code
            return candidates[0].hsn_code
    except Exception:
        # ignore DB errors
        pass

    # try broader similarity: search by common HSN lengths 8,6,4
    for length in (8, 6, 4):
        prefix = norm[:length]
        if not prefix:
            continue
        try:
            candidates = frappe.get_all(
                "GST HSN Code",
                filters=[["hsn_code", "like", f"{prefix}%"]],
                fields=["hsn_code"],
                limit=20,
            )
            for c in candidates:
                # use is_similar helper to match variable lengths
                if is_similar(c.hsn_code, prefix) or is_similar(prefix, c.hsn_code):
                    return c.hsn_code
            if candidates:
                return candidates[0].hsn_code
        except Exception:
            pass

    return None


def load_products_data(json_file):
    """Load products.json data from the data directory."""
    data_path = os.path.join(os.path.dirname(__file__), "data", json_file)
    if not os.path.exists(data_path):
        frappe.msgprint(f"products.json not found at: {data_path}")
        return []
    try:
        with open(data_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        frappe.msgprint(f"Failed to load products.json: {e}")
        return []


def get_hsn_fields():
    """Detect HSN and GST fields on Item doctype."""
    hsn_field_candidates = ["gst_hsn_code", "gst_hsn", "hsn_code"]
    hsn_field = next(
        (hf for hf in hsn_field_candidates if frappe.db.has_column("Item", hf)), None
    )

    return hsn_field


def get_defaults():
    """Get default Item Group and UOM."""
    try:
        ig = frappe.get_doc("Item Group", "All Item Groups")
        default_item_group = ig.name
    except Exception:
        default_item_group = "All Item Groups"
    try:
        uom = frappe.get_doc("UOM", "Nos")
    except Exception:
        uom = None
    return default_item_group, uom


def update_item(item, hsn_field, matched_hsn, gst_field, gst):
    """Update existing Item with HSN and GST fields if changed."""
    changed = False
    changed_fields = []
    if hsn_field and matched_hsn and getattr(item, hsn_field, None) != matched_hsn:
        setattr(item, hsn_field, matched_hsn)
        changed = True
        changed_fields.append(hsn_field)
    if gst_field and gst is not None:
        try:
            prev = getattr(item, gst_field, None)
            prev_f = float(prev) if prev not in (None, "") else None
        except Exception:
            prev_f = None
        try:
            newv = float(gst)
        except Exception:
            newv = None
        if newv is not None and prev_f != newv:
            setattr(item, gst_field, newv)
            changed = True
            changed_fields.append(gst_field)
    if changed:
        item.save(ignore_permissions=True)
    return changed, changed_fields


def create_item(item_code, name, item_group, stock_uom, hsn_field, matched_hsn):
    """Create a new Item document."""
    item_exists = frappe.db.exists("Item", item_code)
    new_item = (
        frappe.get_doc("Item", item_code)
        if item_exists is not None
        else (
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_name": name,
                    "item_group": item_group,
                    "stock_uom": stock_uom,
                    "is_stock_item": 0,
                }
            )
        )
    )
    if hsn_field and matched_hsn:
        setattr(new_item, hsn_field, matched_hsn)
    return new_item.save()


def update_item_taxes_from_json(data):
    """
    Updates the Item Tax Template for all items based on a JSON array.
    """
    # 1. Load the JSON data.
    # Replace the path with the actual path to your JSON file.
    # A dictionary to cache the Item Tax Template names to avoid repeated database lookups.
    tax_template_map = {}
    hsn_field = get_hsn_fields()
    company_abbrs = [
        d["abbr"]
        for d in frappe.get_all(
            "Company",
            fields=["abbr"],
        )
    ]
    tax_category = frappe.get_doc("Tax Category", "In-State")

    for idx, item_data in enumerate(data, start=1):
        item_name_from_json = item_data.get("GSTMASTERDISPNAME")
        tax_rate_string = item_data.get("GSTRATEIGSTRATE")
        hsn_from_json = item_data.get("HSNSACCODE")
        stock_uom = "Nos"
        if (
            item_name_from_json
            and item_name_from_json is not None
            and tax_rate_string
            and tax_rate_string is not None
            and hsn_from_json
            and hsn_from_json is not None
        ):
            if "sheets" in item_name_from_json.lower():
                stock_uom = "Sheets"
            elif "pcs" in item_name_from_json.lower():
                stock_uom = "Pcs"

            if not item_name_from_json or not tax_rate_string:
                continue

            # 2. Sanitize and normalize the tax template name.
            # Example: "12 %" -> "GST 12%"
            try:
                rate = int(tax_rate_string.split("%")[0].strip())
                tax_template_names = [
                    f"GST {rate}% - {cabbr}" if rate > 0 else f"Exempted - {cabbr}"
                    for cabbr in company_abbrs
                ]
            except (IndexError, ValueError):
                frappe.msgprint(
                    f"Could not parse tax rate from: {tax_rate_string}",
                )
                continue

            # 3. Find the corresponding Item Tax Template. Use a cache to optimize.
            for tax_template_name in tax_template_names:
                frappe.msgprint(
                    f"Processing item {idx}: '{item_name_from_json}' with tax template '{tax_template_name}'",
                )
                if tax_template_name not in tax_template_map:
                    if not frappe.db.exists("Item Tax Template", tax_template_name):
                        frappe.msgprint(
                            f"Item Tax Template '{tax_template_name}' not found.",
                        )
                        tax_template_map[tax_template_name] = None
                        continue
                    tax_template_map[tax_template_name] = tax_template_name
                frappe.msgprint(
                    f"Found tax template: {tax_template_map[tax_template_name]}"
                )
                hsn_val = find_hsn_match(hsn_from_json)
                frappe.msgprint(f"HSN: {hsn_val}")
                if tax_template_map.get(tax_template_name) and hsn_val is not None:
                    # 5. Update the Item record.
                    frappe.msgprint(f"Fetching item: {item_name_from_json}")
                    try:
                        item_doc = create_item(
                            item_name_from_json,
                            item_name_from_json,
                            "All Item Groups",
                            stock_uom,
                            hsn_field,
                            hsn_val,
                        )

                        tax_category_name = tax_category.name
                        if (
                            item_doc
                            and item_doc is not None
                            and tax_category_name is not None
                        ):
                            frappe.msgprint("Updating item taxes")
                            item_doc.append(
                                "taxes",
                                {
                                    "item_tax_template": tax_template_name,
                                    "tax_category": tax_category.name,
                                    "minimum_net_rate": 0,
                                    "maximum_net_rate": 0,
                                },
                            )
                        item_doc.save()
                        frappe.msgprint("Updated taxes")
                        frappe.db.commit()
                    except Exception as ex:
                        frappe.msgprint(f"Unable to update taxes: {ex}")
                        frappe.db.rollback()
    frappe.msgprint("Item taxes update process completed.")


def execute():
    # """Import products from products.json as Item records."""
    # filenames = ["products.json", "products_2.json"]
    # for file_name in filenames:
    #     rows = load_products_data(file_name)
    #     if not rows:
    #         return
    #     total = len(rows)

    #     frappe.msgprint(f"Starting products import: {total} rows in file {file_name}")
    #     update_item_taxes_from_json(rows)
    #     frappe.msgprint(
    #         f"Completed item tax template updates from JSON data from {file_name}"
    #     )
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

            except Exception as e:
                frappe.msgprint(
                    f"Error updating Item {item_name} (HSN {item_hsn}): {e}",
                    "Item Tax Update Error",
                    indicator="red",
                )
                frappe.db.rollback()  # Rollback on error
