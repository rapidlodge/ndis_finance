frappe.query_reports["NDIS Executive Action Plan Overdue Report"] = {
    filters: [
        { fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
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
        }
    ]
};
