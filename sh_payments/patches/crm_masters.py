import csv
import json
import logging
import os
import traceback
from typing import Any, Dict, Generator, List

import frappe
import pandas as pd
from frappe.exceptions import NotFound
from frappe.model.document import Document

# Constants for DocTypes and other magic strings
CUSTOMER_DOCTYPE = "Customer"
SUPPLIER_DOCTYPE = "Supplier"
ADDRESS_DOCTYPE = "Address"
DYNAMIC_LINK_DOCTYPE = "Dynamic Link"


class CSVProcessor:
    """
    Processes CSV files to create or update Customer and Supplier documents and their addresses in Frappe.
    """

    def __init__(self, data_csv_base_path: str):
        self.data_csv_base_path = data_csv_base_path
        result_dir = os.path.join(self.data_csv_base_path, "result")
        os.makedirs(result_dir, exist_ok=True)

        self.paths = {
            "addr_res": os.path.join(result_dir, "addresses.txt"),
            "cust_res": os.path.join(result_dir, "customers.txt"),
            "supp_res": os.path.join(result_dir, "suppliers.txt"),
            "addr_err": os.path.join(result_dir, "addr_err.txt"),
            "cust_err": os.path.join(result_dir, "customers_err.txt"),
            "supp_err": os.path.join(result_dir, "suppliers_err.txt"),
            "processed": os.path.join(result_dir, "processed.txt"),
            "log": os.path.join(result_dir, "crm_masters_err.log"),
        }

        # Clean up old result files to ensure a fresh run
        for path in self.paths.values():
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    print(f"Error removing file {path}: {e}")

        logging.basicConfig(
            filename=self.paths["log"],
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

    @staticmethod
    def _get_pan_from_gstin(gstin: str) -> str:
        """Extracts PAN from a GSTIN number."""
        if gstin and len(gstin) >= 12:
            return gstin[2:12]
        return ""

    @staticmethod
    def _clean_gstin(gstin: str) -> str:
        """Cleans and validates GSTIN. Returns empty string if invalid."""
        if not gstin:
            return ""

        gstin = gstin.strip().upper()

        # GSTIN should be exactly 15 characters
        if len(gstin) != 15:
            return ""

        # Basic format check - should be alphanumeric
        if not gstin.isalnum():
            return ""

        return gstin

    @staticmethod
    def _clean_name(name: str) -> str:
        """Cleans name to remove invalid characters for Frappe naming."""
        if not name:
            return ""

        # Remove or replace special characters that cause naming issues
        import re

        name = name.strip()
        # Replace problematic characters
        name = re.sub(r'[<>"&]', "", name)
        # Replace multiple spaces with single space
        name = re.sub(r"\s+", " ", name)
        # Remove leading/trailing spaces
        name = name.strip()

        return name

    @staticmethod
    def _read_csv_rows(filename: str) -> Generator[Dict[str, Any], None, None]:
        """A generator to read a CSV file row by row, handling potential encoding errors."""
        try:
            with open(filename, "r", newline="", encoding="utf-8") as csvfile:
                for row in csv.DictReader(csvfile):
                    yield row
        except UnicodeDecodeError:
            logging.warning(
                f"UTF-8 decoding failed for {filename}. Trying with 'latin-1'."
            )
            with open(filename, "r", newline="", encoding="latin-1") as csvfile:
                for row in csv.DictReader(csvfile):
                    yield row
        except Exception as e:
            logging.error(f"Could not read CSV file {filename}: {e}")
            return

    def get_linked_addresses(self, link_doctype: str, link_name: str) -> List[str]:
        """Finds the names of all Address documents linked to a specific document."""
        try:
            return frappe.get_list(
                doctype=ADDRESS_DOCTYPE,
                filters=[
                    [DYNAMIC_LINK_DOCTYPE, "link_doctype", "=", link_doctype],
                    [DYNAMIC_LINK_DOCTYPE, "link_name", "=", link_name],
                ],
                fields=["name"],
                pluck="name",
            )
        except NotFound as e:
            logging.error(f"Error fetching linked addresses for {link_name}: {e}")
            return []

    def has_address(self, doctype: str, name: str) -> bool:
        """Checks if a document has any linked addresses."""
        return bool(self.get_linked_addresses(doctype, name))

    @staticmethod
    def find_district_by_pincode(pincode_df: pd.DataFrame, pincode: str) -> List[str]:
        """Finds district(s) for a given pincode from the dataframe."""
        if not pincode:
            return []
        try:
            pincode_int = int(pincode)
            results = pincode_df[pincode_df["Pincode"] == pincode_int][
                "District"
            ].unique()
            return results.tolist()
        except (ValueError, TypeError):
            logging.error(f"Invalid pincode format: {pincode}")
            return []

    def _prepare_doc_data(self, row: Dict[str, Any], doctype: str) -> Dict[str, Any]:
        """Prepares a dictionary of data for a Customer or Supplier from a CSV row."""
        # Get the appropriate name field based on doctype
        if doctype == SUPPLIER_DOCTYPE:
            name = self._clean_name(row.get("supplier_name", ""))
            type_field = row.get("supplier_type", "").strip()
        else:
            name = self._clean_name(row.get("customer_name", ""))
            type_field = row.get("customer_type", "").strip()

        gstin = self._clean_gstin(row.get("gstin", ""))

        return {
            "name": name,
            "gstin": gstin,
            "pan": self._get_pan_from_gstin(gstin),
            "group": "Commercial" if doctype == CUSTOMER_DOCTYPE else "Services",
            "type": "Company",
            "currency": "INR",
            "addressLine1": row.get("address", "").strip(),
            "pinCode": row.get("pincode", "").strip(),
            "state": row.get("state", "").strip(),
            "registrationType": type_field,
        }

    def _create_address(
        self,
        doctype: str,
        link_name: str,
        doc_data: Dict[str, Any],
        pincode_df: pd.DataFrame,
    ) -> Document | None:
        """Creates and saves an Address document."""
        pincode = doc_data.get("pinCode") or ""
        districts = self.find_district_by_pincode(pincode_df, pincode)

        # If no district found, use the state as city or a default
        if not districts:
            if pincode:
                logging.error(
                    f"No district found for pincode {pincode} for {link_name}"
                )
            # Use state as city if available, otherwise use a default
            city = doc_data.get("state", "Unknown").strip()
            if not city:
                city = "Unknown"
        else:
            city = districts[0]

        address_type = "Billing" if doctype == CUSTOMER_DOCTYPE else "Shipping"
        gst_category = "Unregistered" if not doc_data["gstin"] else "Registered Regular"

        # Clean up address line to avoid issues
        address_line1 = doc_data["addressLine1"]
        if not address_line1:
            address_line1 = "Address not provided"

        # Validate state - use Karnataka as default if empty or invalid
        state = doc_data.get("state", "").strip()
        if not state or state.lower() in ["unknown", "null", "none", ""]:
            state = "Karnataka"  # Default to Karnataka since most addresses seem to be from Karnataka

        # Clean pincode for validation
        clean_pincode = ""
        if pincode:
            try:
                # Only include if it's a valid 6-digit number
                if (
                    pincode.isdigit()
                    and len(pincode) == 6
                    and not pincode.startswith("0")
                ):
                    clean_pincode = pincode
            except Exception:
                pass

        address_doc = frappe.get_doc(
            {
                "doctype": ADDRESS_DOCTYPE,
                "address_title": f"{link_name} Address",
                "gstin": doc_data["gstin"],
                "pan": doc_data["pan"],
                "gst_category": gst_category,
                "links": [
                    {
                        "doctype": DYNAMIC_LINK_DOCTYPE,
                        "link_doctype": doctype,
                        "link_name": link_name,
                    }
                ],
                "address_type": address_type,
                "address_line1": address_line1,
                "state": state,
                "city": city,
                "country": "India",
                "pincode": clean_pincode,
                "is_primary_address": 1,
            }
        )
        try:
            return address_doc.save(ignore_permissions=True)
        except (frappe.ValidationError, frappe.DuplicateEntryError) as e:
            logging.error(
                f"Validation/Duplicate error for address of {doctype} {link_name}: {e}"
            )
            return None
        except Exception:
            logging.error(
                f"Unexpected error saving address for {doctype} {link_name}:\n{traceback.format_exc()}"
            )
            return None

    def _create_party(self, doctype: str, doc_data: Dict[str, Any]) -> Document | None:
        """Creates and saves a Customer or Supplier document."""
        party_doc = frappe.get_doc(
            {
                "doctype": doctype,
                "default_currency": doc_data["currency"],
                "gstin": doc_data["gstin"],
                "pan": doc_data["pan"],
                "gst_category": "Unregistered"
                if not doc_data["gstin"]
                else "Registered Regular",
            }
        )

        if doctype == SUPPLIER_DOCTYPE:
            setattr(party_doc, "supplier_name", doc_data["name"])
            setattr(party_doc, "supplier_type", doc_data["type"])
            setattr(party_doc, "supplier_group", doc_data["group"])
            setattr(party_doc, "default_price_list", "Standard Buying")
        elif doctype == CUSTOMER_DOCTYPE:
            setattr(party_doc, "customer_name", doc_data["name"])
            setattr(party_doc, "customer_type", doc_data["type"])
            setattr(party_doc, "customer_group", doc_data["group"])
            setattr(party_doc, "default_price_list", "Standard Selling")

        try:
            return party_doc.save(ignore_permissions=True)
        except (frappe.ValidationError, frappe.DuplicateEntryError) as e:
            logging.error(
                f"Validation/Duplicate error for {doctype} {doc_data['name']}: {e}"
            )
            return None
        except Exception:
            logging.error(
                f"Unexpected error saving {doctype} {doc_data['name']}:\n{traceback.format_exc()}"
            )
            return None

    def process_csv_data(
        self,
        file_path: str,
        doctype: str,
        pincode_df: pd.DataFrame,
    ):
        if not os.path.exists(file_path):
            logging.error(f"CSV file not found: {file_path}")
            return f"Skipped: {os.path.basename(file_path)} not found."

        results = {
            "total": 0,
            "existing": 0,
            "processed": [],
            "errors": [],
            "addresses": [],
            "addr_errors": [],
        }

        try:
            # Get the correct field name for each doctype
            name_field_in_csv = (
                "supplier_name" if doctype == SUPPLIER_DOCTYPE else "customer_name"
            )
            csv_doc_names = [
                row.get(name_field_in_csv, "").replace('"', "").strip()
                for row in self._read_csv_rows(file_path)
            ]
        except Exception as e:
            logging.error(f"Failed to read CSV file {file_path}: {e}")
            return f"Error reading {os.path.basename(file_path)}."

        name_field = "supplier_name" if doctype == SUPPLIER_DOCTYPE else "customer_name"
        existing_docs = set(
            frappe.get_all(
                doctype, filters={name_field: ("in", csv_doc_names)}, pluck="name"
            )
        )
        results["existing"] = len(existing_docs)

        for row in self._read_csv_rows(filename=file_path):
            try:
                results["total"] += 1
                doc_data = self._prepare_doc_data(row, doctype)
                doc_name = doc_data["name"]

                if not doc_name:
                    logging.warning(f"Skipping row with empty name: {row}")
                    continue

                if doc_name in existing_docs:
                    if not self.has_address(doctype=doctype, name=doc_name):
                        address = self._create_address(
                            doctype, doc_name, doc_data, pincode_df
                        )
                        if address:
                            results["addresses"].append(address.name)
                        else:
                            results["addr_errors"].append(doc_name)
                else:
                    saved_doc = self._create_party(doctype, doc_data)
                    if saved_doc and getattr(saved_doc, "name", None):
                        results["processed"].append(saved_doc.name)
                        if saved_doc.name is not None:
                            address = self._create_address(
                                doctype, saved_doc.name, doc_data, pincode_df
                            )
                            if address:
                                results["addresses"].append(address.name)
                            else:
                                results["addr_errors"].append(doc_name + " (Address)")
                        else:
                            results["addr_errors"].append(doc_name + " (No Name)")
                    else:
                        results["errors"].append(json.dumps(doc_data))
            except Exception as e:
                logging.error(
                    f"Failed to process row: {row}. Error: {e}\n{traceback.format_exc()}"
                )
                results["errors"].append(json.dumps({"row": row, "error": str(e)}))

        # Write results to files
        self._write_results(doctype, results)

        return (
            f"Total: {results['total']}, "
            f"Existing: {results['existing']}, "
            f"Processed: {len(results['processed'])}, "
            f"Errors: {len(results['errors'])}"
        )

    def _write_results(self, doctype: str, results: Dict[str, Any]):
        """Writes the processing results to their respective files."""
        # Write shared files in append mode
        if results["processed"]:
            pd.Series(results["processed"]).to_csv(
                self.paths["processed"], mode="a", index=False, header=False
            )
        if results["addresses"]:
            pd.Series(results["addresses"]).to_csv(
                self.paths["addr_res"], mode="a", index=False, header=False
            )
        if results["addr_errors"]:
            pd.Series(results["addr_errors"]).to_csv(
                self.paths["addr_err"], mode="a", index=False, header=False
            )

        # Doctype-specific files are not shared, no lock needed, use write mode.
        path_map = {
            SUPPLIER_DOCTYPE: ("supp_res", "supp_err"),
            CUSTOMER_DOCTYPE: ("cust_res", "cust_err"),
        }
        res_path, err_path = path_map.get(doctype, (None, None))
        if res_path and results["processed"]:
            pd.Series(results["processed"]).to_csv(self.paths[res_path], index=False)
        if err_path and results["errors"]:
            pd.Series(results["errors"]).to_csv(self.paths[err_path], index=False)


def process_doctype_task(processor, file_path, doctype, pincode_df):
    """
    Task for processing a single doctype's CSV file.
    Manages its own database transaction.
    """
    try:
        result = processor.process_csv_data(
            file_path=file_path,
            doctype=doctype,
            pincode_df=pincode_df,
        )
        frappe.db.commit()
        logging.info(f"Successfully processed and committed {doctype}.")
        return result
    except Exception:
        logging.error(
            f"Error processing {doctype}. Rolling back changes.\n{traceback.format_exc()}"
        )
        frappe.db.rollback()
        # Re-raise to be caught by the caller
        raise


def execute():
    """Main execution function."""
    base_path = os.path.join(os.path.dirname(__file__), "data")
    processor = CSVProcessor(data_csv_base_path=base_path)
    paths = {
        "customers": os.path.join(base_path, "customers_1.csv"),
        "suppliers": os.path.join(base_path, "suppliers_1.csv"),
        "pincodes": os.path.join(base_path, "pincodes.csv"),
    }

    try:
        pincode_df = pd.read_csv(paths["pincodes"])
    except FileNotFoundError:
        print(f"CRITICAL: Pincode file not found at {paths['pincodes']}. Aborting.")
        logging.critical(f"Pincode file not found at {paths['pincodes']}. Aborting.")
        return
    except Exception as e:
        print(f"CRITICAL: Error reading pincode file: {e}. Aborting.")
        logging.critical(f"Error reading pincode file: {e}. Aborting.")
        return

    tasks_to_run = [
        {"doctype": SUPPLIER_DOCTYPE, "file_path": paths["suppliers"]},
        {"doctype": CUSTOMER_DOCTYPE, "file_path": paths["customers"]},
    ]

    # Process each doctype sequentially
    for task in tasks_to_run:
        doctype_name = task["doctype"]
        try:
            result = process_doctype_task(
                processor,
                task["file_path"],
                task["doctype"],
                pincode_df,
            )
            print(f"{doctype_name.upper()}S: {result}")
        except Exception as exc:
            print(f"An error occurred while processing {doctype_name}: {exc}")
            # Error is already logged by the task wrapper

    print("\nProcessing finished.")
