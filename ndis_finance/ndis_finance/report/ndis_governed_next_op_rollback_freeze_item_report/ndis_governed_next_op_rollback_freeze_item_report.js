frappe.query_reports["NDIS Governed Next Op Rollback Freeze Item Report"] = {
    filters: [
        {
            fieldname: "freeze",
            label: __("Freeze"),
            fieldtype: "Link",
            options: "NDIS Governed Next Op Rollback Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
