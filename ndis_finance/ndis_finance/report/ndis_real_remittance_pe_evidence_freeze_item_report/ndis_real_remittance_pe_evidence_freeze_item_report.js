frappe.query_reports["NDIS Real Remittance PE Evidence Freeze Item Report"] = {
    filters: [
        {
            fieldname: "evidence_freeze",
            label: __("Evidence Freeze"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Evidence Freeze"
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
