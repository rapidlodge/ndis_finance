frappe.query_reports["NDIS Real Remittance Batch Design Exception Report"] = {
    filters: [
        {
            fieldname: "design_gate",
            label: __("Design Gate"),
            fieldtype: "Link",
            options: "NDIS Real Remittance Batch Design Gate"
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
