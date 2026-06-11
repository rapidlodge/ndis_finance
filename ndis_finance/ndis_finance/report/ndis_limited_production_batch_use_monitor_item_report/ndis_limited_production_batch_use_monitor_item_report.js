frappe.query_reports["NDIS Limited Production Batch Use Monitor Item Report"] = {
    filters: [
        {
            fieldname: "monitor_gate",
            label: __("Monitor Gate"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Use Monitor Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
