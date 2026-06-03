frappe.query_reports["NDIS Controlled Production Batch Smoke Line Report"] = {
    filters: [
        {
            fieldname: "smoke_run",
            label: __("Smoke Run"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Smoke Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nSubmitted\nFailed\nCancelled"
        }
    ]
};
