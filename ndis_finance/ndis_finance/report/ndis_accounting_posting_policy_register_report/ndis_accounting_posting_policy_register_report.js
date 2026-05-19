frappe.query_reports["NDIS Accounting Posting Policy Register Report"] = {
    filters: [
        {
            fieldname: "policy_status",
            label: __("Policy Status"),
            fieldtype: "Select",
            options: "\nDraft\nActive\nSuspended\nRetired"
        },
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nClaim Batch\nRemittance\nRecovery Receipt\nRecovery Write Off\nPayroll Cost Import\nCost Pool Allocation\nGovernance Pack\nOther"
        },
        { fieldname: "source_doctype", label: __("Source DocType"), fieldtype: "Data" },
        {
            fieldname: "posting_mode",
            label: __("Posting Mode"),
            fieldtype: "Select",
            options: "\nManagement Only\nPreview Only\nFuture Controlled Posting\nDisabled"
        }
    ]
};
