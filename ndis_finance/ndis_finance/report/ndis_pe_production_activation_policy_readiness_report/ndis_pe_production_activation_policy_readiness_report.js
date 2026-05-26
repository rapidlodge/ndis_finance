frappe.query_reports["NDIS PE Production Activation Policy Readiness Report"] = {
    filters: [
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nPaid Claim\nShort Paid Claim\nRejected Claim\nWrite Off\nCancelled Claim\nManual Override\nXero Export"
        },
        {
            fieldname: "posting_decision",
            label: __("Posting Decision"),
            fieldtype: "Select",
            options: "\nEligible After Approval\nNever Post Payment Entry\nManual Review Required"
        },
        {
            fieldname: "readiness_status",
            label: __("Readiness Status"),
            fieldtype: "Select",
            options: "\nReady\nBlocked By Design\nNeeds Mapping\nNeeds Review\nBlocked - Live Enabled\nBlocked - Cross-company Allowed\nBlocked - Overpayment Allowed\nBlocked - Negative Receipt Allowed"
        }
    ]
};
