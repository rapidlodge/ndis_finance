frappe.query_reports["NDIS Next Governed Limited Op Planning Phase13L Item Report"] = {
    filters: [
        {
            fieldname: "planning",
            label: __("Planning"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Planning"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
