frappe.query_reports["NDIS Accounting Posting Request Register Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPending Approval\nApproved\nRejected\nDry Run Passed\nDry Run Failed\nBlocked\nCancelled"
        },
        {
            fieldname: "approval_status",
            label: __("Approval Status"),
            fieldtype: "Select",
            options: "\nNot Requested\nPending\nApproved\nRejected"
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
