frappe.query_reports["NDIS Limited Production Batch Enablement Smoke Line Report"] = {
    filters: [
        {
            fieldname: "enablement_smoke",
            label: __("Enablement Smoke"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Smoke Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nEnabled - Rollback Required\nPreview Only\nBlocked\nCancelled"
        }
    ]
};
