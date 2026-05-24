frappe.query_reports["NDIS Sandbox Invoice Test Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nCreated Draft Invoice\nSubmitted Invoice Created\nBlocked\nCancelled\nFailed"
        },
        {
            fieldname: "test_mode",
            label: __("Test Mode"),
            fieldtype: "Select",
            options: "\nDraft Invoice Only\nSubmitted Sandbox Invoice"
        },
        {
            fieldname: "sales_invoice",
            label: __("Sales Invoice"),
            fieldtype: "Link",
            options: "Sales Invoice"
        }
    ]
};
