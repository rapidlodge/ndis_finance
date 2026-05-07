frappe.query_reports["NDIS Automation Exception Report"] = {
    filters: [
        {
            fieldname: "exception_type",
            label: __("Exception Type"),
            fieldtype: "Select",
            options: "\nDue Recovery Cases\nOverdue Recovery Cases\nOpen Leakage Without Case\nClaim Exceptions Without Case\nApproved Drafts Not Sent\nEscalation Candidates",
        },
        {
            fieldname: "escalation_overdue_days",
            label: __("Escalation Overdue Days"),
            fieldtype: "Int",
            default: 3,
        },
        {
            fieldname: "preview_limit",
            label: __("Preview Limit"),
            fieldtype: "Int",
            default: 100,
        },
    ],
};
