frappe.query_reports["NDIS Guarded Adapter Final Policy Decision Item Report"] = {
    filters: [
        {
            fieldname: "decision",
            label: __("Decision"),
            fieldtype: "Link",
            options: "NDIS Guarded Adapter Final Policy Decision"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
