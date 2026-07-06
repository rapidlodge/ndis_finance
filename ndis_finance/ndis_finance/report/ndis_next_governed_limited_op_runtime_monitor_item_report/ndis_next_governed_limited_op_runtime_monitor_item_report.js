frappe.query_reports["NDIS Next Governed Limited Op Runtime Monitor Item Report"] = {
    filters: [
        {
            fieldname: "monitor",
            label: __("Monitor"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Runtime Monitor"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
