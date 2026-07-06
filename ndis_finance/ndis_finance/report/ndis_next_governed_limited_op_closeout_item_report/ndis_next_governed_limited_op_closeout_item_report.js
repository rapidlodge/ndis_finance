frappe.query_reports["NDIS Next Governed Limited Op Closeout Item Report"] = {
    filters: [
        {
            fieldname: "closeout",
            label: __("Closeout"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Closeout"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
