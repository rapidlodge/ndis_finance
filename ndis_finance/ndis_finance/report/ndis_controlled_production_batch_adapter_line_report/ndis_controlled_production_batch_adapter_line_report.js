frappe.query_reports["NDIS Controlled Production Batch Adapter Line Report"] = {
    filters: [
        {
            fieldname: "adapter_run",
            label: __("Adapter Run"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Adapter Run"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nWould Create\nHard Blocked\nValidation Blocked\nCancelled"
        }
    ]
};
