frappe.query_reports["NDIS PE One Submitted Smoke Exception Report"] = {
    filters: [
        {
            fieldname: "submitted_run",
            label: __("Submitted Run"),
            fieldtype: "Link",
            options: "NDIS PE One Submitted Smoke Run"
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
