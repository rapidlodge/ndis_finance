frappe.query_reports["NDIS Payment Entry Sandbox Completion Exception Report"] = {
    filters: [
        {
            fieldname: "completion_gate",
            label: __("Completion Gate"),
            fieldtype: "Link",
            options: "NDIS Payment Entry Sandbox Completion Gate"
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
