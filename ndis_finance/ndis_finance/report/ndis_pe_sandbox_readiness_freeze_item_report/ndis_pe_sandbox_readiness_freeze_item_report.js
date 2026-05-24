frappe.query_reports["NDIS PE Sandbox Readiness Freeze Item Report"] = {
    filters: [
        {
            fieldname: "readiness_freeze",
            label: __("Readiness Freeze"),
            fieldtype: "Link",
            options: "NDIS PE Sandbox Readiness Freeze"
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
