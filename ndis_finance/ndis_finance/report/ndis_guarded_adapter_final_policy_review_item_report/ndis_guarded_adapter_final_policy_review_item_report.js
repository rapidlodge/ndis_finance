frappe.query_reports["NDIS Guarded Adapter Final Policy Review Item Report"] = {
    filters: [
        {
            fieldname: "review",
            label: __("Review"),
            fieldtype: "Link",
            options: "NDIS Guarded Adapter Final Policy Review"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
