frappe.query_reports["NDIS PE Production Policy Register"] = {
    filters: [
        {
            fieldname: "policy_status",
            label: __("Policy Status"),
            fieldtype: "Select",
            options: "\nDraft\nDesign Approved\nNeeds Review\nBlocked\nInactive"
        },
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nPaid Claim\nShort Paid Claim\nRejected Claim\nWrite Off\nCancelled Claim\nManual Override\nXero Export"
        },
        {
            fieldname: "production_posting_enabled",
            label: __("Production Posting Enabled"),
            fieldtype: "Select",
            options: "\n0\n1"
        }
    ]
};
