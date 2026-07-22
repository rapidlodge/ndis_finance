frappe.query_reports["NDIS Next Governed Limited Op Design Phase14K Item Report"] = {
    filters: [
        {
            fieldname: "design",
            label: __("Design"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Design"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
