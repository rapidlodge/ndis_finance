frappe.query_reports["NDIS Next Controlled Cycle Plan Item Report"] = {
    filters: [
        {
            fieldname: "planning",
            label: __("Planning"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Planning"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
