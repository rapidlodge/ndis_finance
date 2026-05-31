frappe.query_reports["NDIS PE Smoke Rollback Exception Report"] = {
    filters: [
        {
            fieldname: "rollback_run",
            label: __("Rollback Run"),
            fieldtype: "Link",
            options: "NDIS PE Smoke Rollback Run"
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
