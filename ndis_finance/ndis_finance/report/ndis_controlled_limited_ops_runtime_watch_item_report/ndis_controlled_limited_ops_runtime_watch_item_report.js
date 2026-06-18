frappe.query_reports["NDIS Controlled Limited Ops Runtime Watch Item Report"] = {
    filters: [
        {
            fieldname: "watch",
            label: __("Runtime Watch"),
            fieldtype: "Link",
            options: "NDIS Controlled Limited Ops Runtime Watch"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
