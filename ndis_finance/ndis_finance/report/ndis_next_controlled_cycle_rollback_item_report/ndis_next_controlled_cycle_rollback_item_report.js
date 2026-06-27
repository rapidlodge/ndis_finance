frappe.query_reports["NDIS Next Controlled Cycle Rollback Item Report"] = {
    filters: [
        {
            fieldname: "rollback",
            label: __("Rollback"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Rollback"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
