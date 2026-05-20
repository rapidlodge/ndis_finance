frappe.query_reports["NDIS Accounting Design Matrix Report"] = {
    filters: [
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nClaim Batch\nRemittance\nRecovery Receipt\nRecovery Write Off\nPayroll Cost Import\nCost Pool Allocation\nGovernance Pack\nXero Export\nOther"
        },
        {
            fieldname: "design_status",
            label: __("Design Status"),
            fieldtype: "Select",
            options: "\nDraft\nActive\nSuspended\nRetired"
        },
        {
            fieldname: "risk_level",
            label: __("Risk Level"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical"
        },
        {
            fieldname: "allowed_target_doctype",
            label: __("Allowed Target DocType"),
            fieldtype: "Select",
            options: "\nNone\nSales Invoice\nPayment Entry\nJournal Entry\nPurchase Invoice\nExternal System"
        }
    ]
};
