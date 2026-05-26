frappe.query_reports["NDIS PE Submitted Smoke Exception Report"] = {
    filters: [
        {
            fieldname: "submitted_smoke_gate",
            label: __("Submitted Smoke Gate"),
            fieldtype: "Link",
            options: "NDIS PE Submitted Smoke Gate"
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
