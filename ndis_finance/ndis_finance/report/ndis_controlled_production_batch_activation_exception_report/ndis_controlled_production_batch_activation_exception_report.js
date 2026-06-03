frappe.query_reports["NDIS Controlled Production Batch Activation Exception Report"] = {
    filters: [
        {
            fieldname: "activation_gate",
            label: __("Activation Gate"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Activation Gate"
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
