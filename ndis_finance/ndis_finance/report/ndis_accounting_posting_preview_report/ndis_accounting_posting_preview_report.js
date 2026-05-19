frappe.query_reports["NDIS Accounting Posting Preview Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nBlocked\nCancelled"
        },
        {
            fieldname: "validation_status",
            label: __("Validation Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocked"
        },
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nClaim Batch\nRemittance\nRecovery Receipt\nRecovery Write Off\nPayroll Cost Import\nCost Pool Allocation\nGovernance Pack\nOther"
        },
        { fieldname: "policy", label: __("Policy"), fieldtype: "Link", options: "NDIS Accounting Posting Policy" },
        { fieldname: "source_doctype", label: __("Source DocType"), fieldtype: "Data" }
    ]
};
