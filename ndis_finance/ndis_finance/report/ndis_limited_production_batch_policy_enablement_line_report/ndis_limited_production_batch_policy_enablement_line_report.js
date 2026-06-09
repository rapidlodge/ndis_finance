frappe.query_reports["NDIS Limited Production Batch Policy Enablement Line Report"] = {
    filters: [
        {
            fieldname: "enablement_run",
            label: __("Enablement Run"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Policy Enablement Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nEnabled\nPreview Only\nBlocked\nCancelled"
        }
    ]
};
