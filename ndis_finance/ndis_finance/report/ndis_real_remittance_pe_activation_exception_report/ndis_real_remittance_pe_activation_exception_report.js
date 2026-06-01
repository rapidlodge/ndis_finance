frappe.query_reports["NDIS Real Remittance PE Activation Exception Report"] = {
    filters: [
        {
            fieldname: "activation_gate",
            label: __("Activation Gate"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Activation Gate"
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
