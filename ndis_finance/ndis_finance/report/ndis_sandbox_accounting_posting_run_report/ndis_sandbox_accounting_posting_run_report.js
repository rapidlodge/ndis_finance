frappe.query_reports["NDIS Sandbox Accounting Posting Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nDry Run\nCreated Draft JE\nBlocked\nCancelled\nFailed"
        },
        { fieldname: "posting_request", label: __("Posting Request"), fieldtype: "Link", options: "NDIS Accounting Posting Request" },
        { fieldname: "journal_entry", label: __("Draft Journal Entry"), fieldtype: "Link", options: "Journal Entry" }
    ]
};
