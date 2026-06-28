frappe.query_reports["NDIS Next Controlled Cycle Closeout Item Report"] = {
    filters: [
        {
            fieldname: "closeout",
            label: __("Closeout"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Closeout"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
