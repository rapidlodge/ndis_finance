frappe.query_reports["NDIS Real Remittance Batch Source Harness Line Report"] = {
    filters: [
        {
            fieldname: "source_run",
            label: __("Source Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance Batch Source Harness Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nReady\nNeeds Review\nBlocked\nCancelled"
        }
    ]
};
