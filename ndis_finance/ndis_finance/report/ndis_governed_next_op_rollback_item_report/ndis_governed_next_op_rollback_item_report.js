frappe.query_reports["NDIS Governed Next Op Rollback Item Report"] = {
    filters: [
        {
            fieldname: "rollback",
            label: __("Rollback"),
            fieldtype: "Link",
            options: "NDIS Governed Next Op Rollback"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};