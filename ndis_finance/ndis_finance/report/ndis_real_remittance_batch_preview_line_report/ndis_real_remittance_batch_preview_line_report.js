frappe.query_reports["NDIS Real Remittance Batch Preview Line Report"] = {
    filters: [
        {
            fieldname: "batch_preview",
            label: __("Batch Preview"),
            fieldtype: "Link",
            options: "NDIS Real Remittance Batch Preview"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nEligible\nBlocked\nDuplicate\nCap Blocked\nInfo\nCancelled"
        },
        { fieldname: "outcome", label: __("Outcome"), fieldtype: "Data" }
    ]
};
