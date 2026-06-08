frappe.query_reports["NDIS Limited Production Batch Enablement Adapter Line Report"] = {
    filters: [
        {
            fieldname: "enablement_adapter",
            label: __("Enablement Adapter"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Adapter Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nHard Blocked\nValidation Blocked\nCancelled"
        }
    ]
};
