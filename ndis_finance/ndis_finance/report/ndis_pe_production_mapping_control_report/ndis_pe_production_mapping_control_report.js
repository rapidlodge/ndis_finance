frappe.query_reports["NDIS PE Production Mapping Control Report"] = {
    filters: [
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nPaid Claim\nShort Paid Claim\nRejected Claim\nWrite Off\nCancelled Claim\nManual Override\nXero Export"
        },
        {
            fieldname: "policy_status",
            label: __("Policy Status"),
            fieldtype: "Select",
            options: "\nDraft\nDesign Approved\nNeeds Review\nBlocked\nInactive"
        },
        {
            fieldname: "missing_accounts_only",
            label: __("Missing Accounts Only"),
            fieldtype: "Check"
        }
    ]
};
