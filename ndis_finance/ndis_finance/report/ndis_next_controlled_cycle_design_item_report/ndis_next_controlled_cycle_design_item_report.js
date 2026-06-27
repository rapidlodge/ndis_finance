frappe.query_reports["NDIS Next Controlled Cycle Design Item Report"] = {
    filters: [
        {
            fieldname: "design",
            label: __("Design"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Design"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
