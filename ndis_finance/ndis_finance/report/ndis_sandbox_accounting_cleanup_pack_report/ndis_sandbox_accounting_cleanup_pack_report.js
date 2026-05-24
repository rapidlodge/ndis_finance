frappe.query_reports["NDIS Sandbox Accounting Cleanup Pack Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nCleaned\nBlocked\nCancelled\nFailed"
        },
        {
            fieldname: "cleanup_scope",
            label: __("Cleanup Scope"),
            fieldtype: "Select",
            options: "\nPayment Entry Drafts + Submitted Sandbox Invoices\nPayment Entry Drafts Only\nSubmitted Sandbox Invoices Only"
        }
    ]
};
