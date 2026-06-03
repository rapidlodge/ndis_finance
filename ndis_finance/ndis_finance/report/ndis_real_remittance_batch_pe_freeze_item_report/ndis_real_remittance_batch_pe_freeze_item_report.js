frappe.query_reports["NDIS Real Remittance Batch PE Freeze Item Report"] = {
    filters: [
        {
            fieldname: "freeze",
            label: __("Freeze"),
            fieldtype: "Link",
            options: "NDIS Real Remittance Batch PE Evidence Freeze"
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
        }
    ]
};
