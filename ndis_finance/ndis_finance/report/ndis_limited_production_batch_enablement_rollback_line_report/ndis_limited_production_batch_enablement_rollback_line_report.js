frappe.query_reports["NDIS Limited Production Batch Enablement Rollback Line Report"] = {
    filters: [
        {
            fieldname: "rollback_run",
            label: __("Rollback Run"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Rollback Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nRolled Back\nPreview Only\nBlocked\nCancelled"
        }
    ]
};
