frappe.query_reports["NDIS Single Guarded Limited Operation Smoke Rollback Item Report"] = {
    filters: [
        {
            fieldname: "rollback",
            label: __("Rollback"),
            fieldtype: "Link",
            options: "NDIS Single Guarded Limited Operation Smoke Rollback"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};