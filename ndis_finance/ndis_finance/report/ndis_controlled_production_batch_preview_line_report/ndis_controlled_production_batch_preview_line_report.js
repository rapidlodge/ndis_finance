frappe.query_reports["NDIS Controlled Production Batch Preview Line Report"] = {
    filters: [
        {
            fieldname: "preview",
            label: __("Preview"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Preview"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nEligible\nBlocked\nDuplicate\nCancelled"
        }
    ]
};
