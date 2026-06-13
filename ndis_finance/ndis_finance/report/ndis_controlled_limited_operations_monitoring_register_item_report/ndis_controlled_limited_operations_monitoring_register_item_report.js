frappe.query_reports["NDIS Controlled Limited Operations Monitoring Register Item Report"] = {
    filters: [
        {
            fieldname: "register",
            label: __("Register"),
            fieldtype: "Link",
            options: "NDIS Controlled Limited Operations Monitoring Register"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
