frappe.query_reports["NDIS Limited Production Batch Enablement Preview Line Report"] = {
    filters: [
        {
            fieldname: "enablement_preview",
            label: __("Enablement Preview"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Preview"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nWould Enable\nBlocked\nCancelled"
        }
    ]
};
