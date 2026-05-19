frappe.query_reports["NDIS Finance Readiness Exception Report"] = {
    filters: [
        { fieldname: "readiness_check", label: __("Readiness Check"), fieldtype: "Link", options: "NDIS Finance Production Readiness Check" },
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
