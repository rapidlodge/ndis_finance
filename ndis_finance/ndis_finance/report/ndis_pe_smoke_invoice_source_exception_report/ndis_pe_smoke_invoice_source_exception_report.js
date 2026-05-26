frappe.query_reports["NDIS PE Smoke Invoice Source Exception Report"] = {
    filters: [
        {
            fieldname: "source_run",
            label: __("Source Run"),
            fieldtype: "Link",
            options: "NDIS PE Smoke Invoice Source Run"
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
