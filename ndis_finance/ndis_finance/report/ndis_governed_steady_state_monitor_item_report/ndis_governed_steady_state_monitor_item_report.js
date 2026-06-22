frappe.query_reports["NDIS Governed Steady State Monitor Item Report"] = {
    filters: [
        {
            fieldname: "monitor",
            label: __("Monitor"),
            fieldtype: "Link",
            options: "NDIS Governed Steady State Monitor"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
