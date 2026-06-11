frappe.query_reports["NDIS Limited Batch Runtime Guard Item Report"] = {
    filters: [
        {
            fieldname: "runtime_guard",
            label: __("Runtime Guard"),
            fieldtype: "Link",
            options: "NDIS Limited Batch Runtime Guard"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
