frappe.query_reports["NDIS Invoice Backed PE Smoke Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nValidated\nCompleted\nBlocked\nCancelled\nFailed"
        },
        {
            fieldname: "sales_invoice",
            label: __("Sales Invoice"),
            fieldtype: "Link",
            options: "Sales Invoice"
        },
        {
            fieldname: "payment_entry",
            label: __("Draft Payment Entry"),
            fieldtype: "Link",
            options: "Payment Entry"
        }
    ]
};
