frappe.query_reports["NDIS PE Live Smoke Completion Exception Report"] = {
    filters: [
        {
            fieldname: "completion_freeze",
            label: __("Completion Freeze"),
            fieldtype: "Link",
            options: "NDIS PE Live Smoke Completion Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        },
        {
            fieldname: "severity",
            label: __("Severity"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical"
        },
        { fieldname: "category", label: __("Category"), fieldtype: "Data" }
    ]
};
