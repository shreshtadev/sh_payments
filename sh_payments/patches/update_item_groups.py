import logging

import frappe

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def update_item_group(item_group_name):
    items = frappe.get_all("Item", fields=["name", "item_group"])
    if items:
        for item in items:
            # Update the document using update
            frappe.db.set_value("Item", item["name"], "item_group", item_group_name)


def execute():
    """
    Updating Item Groups
    """
    sa_item_group = frappe.get_doc("Item Group", "Shree Agencies")
    if sa_item_group is not None:
        update_item_group(sa_item_group.name)
    logging.info("Finished Updating ItemGroup for Items")
