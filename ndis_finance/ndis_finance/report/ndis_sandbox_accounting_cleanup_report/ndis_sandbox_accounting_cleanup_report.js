frappe.query_reports["NDIS Sandbox Accounting Cleanup Report"] = {
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
            fieldname: "cleanup_mode",
            label: __("Cleanup Mode"),
            fieldtype: "Select",
            options: "\nPreview Only\nDelete Draft Sandbox JE"
        }
    ]
};
