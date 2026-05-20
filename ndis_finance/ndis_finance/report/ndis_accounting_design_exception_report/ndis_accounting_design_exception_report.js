frappe.query_reports["NDIS Accounting Design Exception Report"] = {
    filters: [
        { fieldname: "design_review", label: __("Design Review"), fieldtype: "Link", options: "NDIS Accounting Design Review" },
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
