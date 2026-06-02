frappe.query_reports["NDIS Real Remittance Batch PE Smoke Line Report"] = {
    filters: [
        {
            fieldname: "smoke_run",
            label: __("Smoke Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance Batch PE Smoke Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nSubmitted\nNeeds Review\nBlocked\nCancelled"
        }
    ]
};
