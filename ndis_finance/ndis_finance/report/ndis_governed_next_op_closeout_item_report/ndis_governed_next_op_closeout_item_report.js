frappe.query_reports["NDIS Governed Next Op Closeout Item Report"] = {
    filters: [
        {
            fieldname: "closeout",
            label: __("Closeout"),
            fieldtype: "Link",
            options: "NDIS Governed Next Op Closeout"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
