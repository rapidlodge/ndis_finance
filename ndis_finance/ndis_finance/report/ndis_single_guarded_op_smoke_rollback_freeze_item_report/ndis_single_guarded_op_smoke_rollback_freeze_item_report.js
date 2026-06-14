frappe.query_reports["NDIS Single Guarded Op Smoke Rollback Freeze Item Report"] = {
    filters: [
        {
            fieldname: "freeze",
            label: __("Freeze"),
            fieldtype: "Link",
            options: "NDIS Single Guarded Op Smoke Rollback Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
