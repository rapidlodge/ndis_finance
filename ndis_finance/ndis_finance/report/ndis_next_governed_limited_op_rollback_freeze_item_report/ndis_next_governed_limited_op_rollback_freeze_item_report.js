frappe.query_reports["NDIS Next Governed Limited Op Rollback Freeze Item Report"] = {
    filters: [
        {
            fieldname: "freeze",
            label: __("Freeze"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Rollback Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
