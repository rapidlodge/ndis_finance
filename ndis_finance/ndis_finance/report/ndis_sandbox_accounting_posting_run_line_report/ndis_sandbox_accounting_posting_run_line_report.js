frappe.query_reports["NDIS Sandbox Accounting Posting Run Line Report"] = {
    filters: [
        { fieldname: "sandbox_run", label: __("Sandbox Run"), fieldtype: "Link", options: "NDIS Sandbox Accounting Posting Run" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPrepared\nInserted In Draft JE\nWarning\nBlocker\nCancelled"
        },
        {
            fieldname: "line_type",
            label: __("Line Type"),
            fieldtype: "Select",
            options: "\nDebit\nCredit"
        },
        { fieldname: "account", label: __("Account"), fieldtype: "Link", options: "Account" }
    ]
};
