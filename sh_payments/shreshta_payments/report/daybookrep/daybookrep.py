# Copyright (c) 2025, shreshtadev and contributors
# For license information, please see license.txt

import frappe

filters = [
    {
        "fieldname": "report_date",
        "label": "Select Date",
        "fieldtype": "Date",
        "default": frappe.utils.today()
    }
]

def execute(filters=None):
    report_date = filters.get("report_date", frappe.utils.today())

    # Calculate Opening Balance
    opening_balance = frappe.db.sql(
        """
        SELECT COALESCE(SUM(
            CASE WHEN payment_type = 'Receipt' THEN total_amount
                 WHEN payment_type = 'Voucher' THEN -total_amount
                 ELSE 0 END
        ), 0) AS opening_balance
        FROM `tabShPayment`
        WHERE payment_date < %(report_date)s
    """, {"report_date": report_date},
        as_dict=True,
    )[0]["opening_balance"]

    # Transactions in the Selected Date Range
    transactions = frappe.db.sql(
        """
        SELECT payment_date, payment_type, total_amount
        FROM `tabShPayment`
        WHERE payment_date = %(report_date)s
    """, {"report_date": report_date},
        as_dict=True,
    )

    # Calculate Closing Balance
    closing_balance = frappe.db.sql(
        """
        SELECT COALESCE(SUM(
            CASE WHEN payment_type = 'Receipt' THEN total_amount
                 WHEN payment_type = 'Voucher' THEN -total_amount
                 ELSE 0 END
        ), 0) AS closing_balance
        FROM `tabShPayment`
        WHERE payment_date <= %(report_date)s
    """, {"report_date": report_date},
        as_dict=True,
    )[0]["closing_balance"]

    # Define Report Columns
    columns = [
        {"fieldname": "payment_date", "label": "Date", "fieldtype": "Date"},
        {"fieldname": "payment_type", "label": "Type", "fieldtype": "Data"},
        {"fieldname": "total_amount", "label": "Amount", "fieldtype": "Currency"},
        {
            "fieldname": "opening_balance",
            "label": "Opening Balance",
            "fieldtype": "Currency",
        },
        {
            "fieldname": "closing_balance",
            "label": "Closing Balance",
            "fieldtype": "Currency",
        },
    ]

    # Prepare Report Data
    data = [
        {
            "payment_date": row["payment_date"],
            "payment_type": row["payment_type"],
            "total_amount": row["total_amount"],
        }
        for row in transactions
    ]

    # Append Opening & Closing Balances
    data.insert(
        0,
        {
            "payment_date": report_date,
            "payment_type": "Opening Balance",
            "total_amount": opening_balance,
        },
    )
    data.append(
        {
            "payment_date": report_date,
            "payment_type": "Closing Balance",
            "total_amount": closing_balance,
        }
    )

    return columns, data
