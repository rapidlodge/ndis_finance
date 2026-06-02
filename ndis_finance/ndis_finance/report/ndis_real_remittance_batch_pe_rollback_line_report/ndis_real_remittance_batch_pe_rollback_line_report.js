frappe.query_reports["NDIS Real Remittance Batch PE Rollback Line Report"] = {
    filters: [
        {
            fieldname: "rollback_run",
            label: __("Rollback Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance Batch PE Rollback Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nRestored\nNeeds Review\nBlocked\nCancelled"
        }
    ]
};
