frappe.query_reports["NDIS PE Production Account Mapping Exception Report"] = {
    filters: [
        {
            fieldname: "mapping_gate",
            label: __("Mapping Gate"),
            fieldtype: "Link",
            options: "NDIS PE Production Account Mapping Gate"
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
