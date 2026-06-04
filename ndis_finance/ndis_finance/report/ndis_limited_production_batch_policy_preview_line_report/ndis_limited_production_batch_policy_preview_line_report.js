frappe.query_reports["NDIS Limited Production Batch Policy Preview Line Report"] = {
    filters: [
        {
            fieldname: "policy_preview",
            label: __("Policy Preview"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Policy Preview"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nEligible\nBlocked\nDuplicate\nCancelled"
        }
    ]
};
