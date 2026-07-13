frappe.query_reports["NDIS Next Governed Limited Op Smoke Rollback Item Report"] = {
    filters: [
        {
            fieldname: "rollback",
            label: __("Rollback"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Smoke Rollback"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
