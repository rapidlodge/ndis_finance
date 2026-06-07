frappe.query_reports["NDIS Limited Production Batch Controlled Smoke Line Report"] = {
    filters: [
        {
            fieldname: "smoke_run",
            label: __("Smoke Run"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Smoke Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nSubmitted\nBlocked\nCancelled"
        }
    ]
};
