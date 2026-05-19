frappe.query_reports["NDIS Executive Action Plan Register Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nIn Progress\nOverdue\nEscalated\nCompleted\nCancelled"
        },
        {
            fieldname: "priority",
            label: __("Priority"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical"
        },
        {
            fieldname: "severity",
            label: __("Severity"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical"
        },
        { fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
        { fieldname: "exception_alert", label: __("Exception Alert"), fieldtype: "Link", options: "NDIS Executive Exception Alert" },
        { fieldname: "from_date", label: __("Due From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Due To Date"), fieldtype: "Date" }
    ]
};
