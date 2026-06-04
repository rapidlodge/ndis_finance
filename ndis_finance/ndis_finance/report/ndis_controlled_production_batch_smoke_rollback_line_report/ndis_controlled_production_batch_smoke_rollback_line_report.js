frappe.query_reports["NDIS Controlled Production Batch Smoke Rollback Line Report"] = {
    filters: [
        {
            fieldname: "rollback_run",
            label: __("Rollback Run"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Smoke Rollback Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nRestored\nFailed\nCancelled"
        }
    ]
};