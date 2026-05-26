frappe.query_reports["NDIS PE Single Record Draft Smoke Exception Report"] = {
    filters: [
        {
            fieldname: "smoke_run",
            label: __("Smoke Run"),
            fieldtype: "Link",
            options: "NDIS PE Single Record Draft Smoke Run"
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
