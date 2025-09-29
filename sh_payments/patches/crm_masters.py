import csv
import json
import logging
import os
import traceback

import frappe
import pandas as pd


class CSVProcessor:
    def __init__(self, data_csv_base_path: str):
        self.data_csv_base_path = data_csv_base_path

        # Create result directory if it doesn't exist
        result_dir = os.path.join(self.data_csv_base_path, "result")
        os.makedirs(result_dir, exist_ok=True)
        self.addr_res_path = os.path.join(result_dir, "addresses.txt")

        self.c_res_path = os.path.join(result_dir, "customers.txt")

        self.s_res_path = os.path.join(result_dir, "suppliers.txt")

        self.addr_err_path = os.path.join(result_dir, "addr_err.txt")

        self.cerr_res_path = os.path.join(result_dir, "customers_err.txt")

        self.serr_res_path = os.path.join(result_dir, "suppliers_err.txt")

        self.prd_path = os.path.join(result_dir, "processed.txt")
        logging.basicConfig(
            filename=os.path.join(result_dir, "crm_masters_err.log"),
            level=logging.ERROR,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

    @staticmethod
    def _get_pan_from_gstin(gstin: str) -> str:
        # PAN is characters 3 to 12 in GSTIN (index 2:12)
        if len(gstin) >= 12:
            return gstin[2:12]
        return ""

    @staticmethod
    def _read_csv_batch(filename: str, batch_size: int = 10):
        """
        A generator to read a CSV file in specified batches.
        """
        batch = []
        with open(filename, "r", newline="") as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                batch.append(row)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            # Yield any remaining rows in the last batch
            if batch:
                yield batch

    @staticmethod
    def _read_csv_row(filename: str):
        """
        A generator to read a CSV file.
        """
        with open(filename, "r", newline="") as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                yield row

    def get_linked_addresses(self, link_doctype: str, link_name: str) -> list[str]:
        linked_records = list()
        address_names = list[str]()
        """
        Finds the names (IDs) of all Address documents linked to a specific document.

        :param client: The authenticated FrappeClient instance.
        :param link_doctype: The DocType of the document to check (e.g., 'Customer').
        :param link_name: The 'name' (ID) of the specific document (e.g., 'CUST/00001').
        :return: A list of Address document names (e.g., ['ADDR00001', 'ADDR00002']).
        """
        # Query the Dynamic Link DocType
        linked_records = frappe.get_list(
            doctype="Address",
            filters=[
                ["Dynamic Link", "link_doctype", "=", link_doctype],
                ["Dynamic Link", "link_name", "=", link_name],
            ],
            # We only need the 'parent' field, which holds the Name (ID) of the Address document.
            fields="name",
        )
        if linked_records is not None:
            # Extract the Address names from the list of dictionaries
            address_names = [record.get("parent") for record in linked_records]

        return address_names

    def has_address(self, doctype, name: str) -> bool:
        """
        Checks if a Customer has any linked addresses using the FrappeClient.
        """
        addresses = self.get_linked_addresses(doctype, name)
        return bool(addresses)

    def find_district_by_pincode(self, indexed_df: pd.DataFrame, pincode: str):
        try:
            result = indexed_df.loc[pincode, "District"]
            if isinstance(result, pd.Series):
                return result.unique().tolist()
            return [result]
        except KeyError:
            return []

    def process_csv_data(self, file_path: str, doctype: str, indexed_df: pd.DataFrame):
        old_docs = []
        total_docs = []
        processed_docs = []
        error_docs = []
        address_docs = []
        addr_err_docs = []

        for row in self._read_csv_row(filename=file_path):
            doc_data = dict[str, str]()
            customer_name = row[
                "TALLYMESSAGE.LEDGER.LANGUAGENAME.LIST.NAME.LIST.NAME.text"
            ]
            customer_name.replace('"', "") if '"' in customer_name else customer_name
            gstin = row["TALLYMESSAGE.LEDGER.LEDGSTREGDETAILS.LIST.GSTIN.text"]
            doc_data["registrationType"] = row[
                "TALLYMESSAGE.LEDGER.GSTREGISTRATIONTYPE.text"
            ]
            doc_data["name"] = customer_name
            doc_data["gstin"] = gstin if gstin is not None else ""
            doc_data["pan"] = self._get_pan_from_gstin(gstin) if gstin != "" else ""
            doc_data["group"] = "Commercial" if doctype == "Customer" else "Services"
            doc_data["type"] = "Company"
            doc_data["currency"] = "INR"
            doc_data["addressLine1"] = row[
                "TALLYMESSAGE.LEDGER.LEDMAILINGDETAILS.LIST.ADDRESS.LIST.ADDRESS.text"
            ]
            doc_data["pinCode"] = row[
                "TALLYMESSAGE.LEDGER.LEDMAILINGDETAILS.LIST.PINCODE.text"
            ]
            doc_data["state"] = row[
                "TALLYMESSAGE.LEDGER.LEDMAILINGDETAILS.LIST.STATE.text"
            ]

            # Check if document exists before trying to get it
            try:
                found_doc = frappe.get_doc(doctype, doc_data.get("name", ""))
            except frappe.exceptions.DoesNotExistError:
                found_doc = None

            total_docs.append(doc_data["name"])

            if found_doc is not None:
                old_docs.append(found_doc.name)
                is_found = self.has_address(doctype=doctype, name=str(found_doc.name))
                found_pincode = self.find_district_by_pincode(
                    indexed_df=indexed_df, pincode=doc_data["pinCode"]
                )
                if not is_found and len(found_pincode) > 0:
                    doc_to_insert = frappe.get_doc(
                        {
                            "doctype": "Address",
                            "gstin": doc_data["gstin"],
                            "pan": doc_data["pan"],
                            "gst_category": "Unregistered"
                            if (doc_data["gstin"] is None or doc_data["gstin"] == "")
                            else "Registered Regular",
                            "links": [
                                {
                                    "doctype": "Dynamic Link",
                                    "link_doctype": doctype,
                                    "link_name": found_doc.name,
                                }
                            ],
                            "address_type": (
                                "Billing" if doctype == "Customer" else "Shipping"
                            ),
                            "address_line1": doc_data["addressLine1"],
                            "state": doc_data["state"],
                            "city": found_pincode[0],
                            "country": "India",
                            "pincode": doc_data["pinCode"],
                            "is_primary_address": 1,
                        }
                    )
                    # doc_to_insert["address_title"] = doc_data["name"] + " Address"

                    try:
                        inserted_addr = doc_to_insert.save()
                        address_docs.append(inserted_addr.name)
                    except Exception:
                        addr_err_docs.append(found_doc.name)
                        exception_detail = traceback.format_exc()
                        logging.error(
                            "An unexpected error occurred during data processing:\n%s",
                            exception_detail,
                        )

            else:
                processed_docs.append(doc_data["name"])
                doc_to_insert = frappe.get_doc(
                    {
                        "doctype": doctype,
                        "default_currency": doc_data["currency"],
                        "gstin": doc_data["gstin"],
                        "pan": doc_data["pan"],
                        "gst_category": "Unregistered"
                        if (doc_data["gstin"] is None or doc_data["gstin"] == "")
                        else "Registered Regular",
                    }
                )

                if doctype == "Supplier":
                    doc_to_insert.set("supplier_name", doc_data["name"])
                    doc_to_insert.set("supplier_type", doc_data["type"])
                    doc_to_insert.set("supplier_group", doc_data["group"])
                    doc_to_insert.set("default_price_list", "Standard Buying")
                elif doctype == "Customer":
                    doc_to_insert.set("customer_name", doc_data["name"])
                    doc_to_insert.set("customer_type", doc_data["type"])
                    doc_to_insert.set("customer_group", doc_data["group"])
                    doc_to_insert.set("default_price_list", "Standard Selling")

                try:
                    found_pincode = self.find_district_by_pincode(
                        indexed_df=indexed_df, pincode=doc_data["pinCode"]
                    )
                    if len(found_pincode) == 0:
                        raise Exception("No Pincode Found. Pincode is mandatory")
                    saved_doc = doc_to_insert.save()
                    address_doc = frappe.get_doc(
                        {
                            "doctype": "Address",
                            "gstin": doc_data["gstin"],
                            "pan": doc_data["pan"],
                            "gst_category": "Unregistered"
                            if (doc_data["gstin"] is None or doc_data["gstin"] == "")
                            else "Registered Regular",
                            "links": [
                                {
                                    "doctype": "Dynamic Link",
                                    "link_doctype": doctype,
                                    "link_name": saved_doc.name,
                                }
                            ],
                            "address_type": (
                                "Billing" if doctype == "Customer" else "Shipping"
                            ),
                            "address_line1": doc_data["addressLine1"],
                            "state": doc_data["state"],
                            "city": found_pincode[0],
                            "pincode": doc_data["pinCode"],
                            "country": "India",
                            "is_primary_address": 1,
                        }
                    )
                    try:
                        saved_address = address_doc.save()
                        address_docs.append(saved_address.name)
                    except Exception:
                        addr_err_docs.append(doc_data["name"] + " Address")
                        exception_detail = traceback.format_exc()
                        logging.error(
                            "An unexpected error occurred during data processing(2):\n%s",
                            exception_detail,
                        )

                except Exception:
                    error_docs.append(json.dumps(doc_data))
                    exception_detail = traceback.format_exc()
                    logging.error(
                        "An unexpected error occurred during data processing(3):\n%s",
                        exception_detail,
                    )

        if len(processed_docs) > 0:
            pd.Series(processed_docs).to_csv(self.prd_path, index=False)
        if len(address_docs) > 0:
            pd.Series(address_docs).to_csv(self.addr_res_path, index=False)
        if len(addr_err_docs) > 0:
            pd.Series(addr_err_docs).to_csv(self.addr_err_path, index=False)
        if doctype == "Supplier":
            if len(processed_docs) > 0:
                pd.Series(processed_docs).to_csv(self.s_res_path, index=False)
            if len(error_docs) > 0:
                pd.Series(error_docs).to_csv(self.serr_res_path, index=False)
        elif doctype == "Customer":
            if len(processed_docs) > 0:
                pd.Series(processed_docs).to_csv(self.c_res_path, index=False)
            if len(error_docs) > 0:
                pd.Series(error_docs).to_csv(self.cerr_res_path, index=False)

        return f"Available {doctype}: {len(total_docs)} Existing {doctype}: {len(old_docs)} Processed {doctype}: {len(processed_docs)} Errors {doctype}: {len(error_docs)}"


def execute():
    DATA_CSV_BASE_PATH = os.path.join(
        os.path.dirname(__file__), "data"
    )  # This can be made dynamic if needed

    customers_csv_path = os.path.join(
        os.path.dirname(__file__), DATA_CSV_BASE_PATH, "customers_1.csv"
    )
    suppliers_csv_path = os.path.join(
        os.path.dirname(__file__), DATA_CSV_BASE_PATH, "suppliers_1.csv"
    )
    pincodes_csv_path = os.path.join(
        os.path.dirname(__file__), DATA_CSV_BASE_PATH, "pincodes.csv"
    )

    processor = CSVProcessor(
        data_csv_base_path=DATA_CSV_BASE_PATH,
    )
    indexed_df = pd.read_csv(pincodes_csv_path).set_index("Pincode")

    supplier_result = processor.process_csv_data(
        file_path=suppliers_csv_path,
        doctype="Supplier",
        indexed_df=indexed_df,
    )
    customer_result = processor.process_csv_data(
        file_path=customers_csv_path,
        doctype="Customer",
        indexed_df=indexed_df,
    )
    frappe.db.commit()

    print(f"SUPPLIERS: {supplier_result} CUSTOMERS: {customer_result}")
