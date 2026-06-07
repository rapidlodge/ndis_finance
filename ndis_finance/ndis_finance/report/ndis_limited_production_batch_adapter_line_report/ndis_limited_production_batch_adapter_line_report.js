frappe.query_reports["NDIS Limited Production Batch Adapter Line Report"] = {
    filters: [
        {
            fieldname: "adapter_run",
            label: __("Adapter Run"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Adapter Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nHard Blocked\nValidation Blocked\nDuplicate Blocked\nCancelled"
        }
    ]
};
