frappe.query_reports["NDIS Guarded Limited Adapter Smoke Rollback Item Report"] = {
    filters: [
        {
            fieldname: "rollback",
            label: __("Rollback"),
            fieldtype: "Link",
            options: "NDIS Guarded Limited Adapter Smoke Rollback"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
