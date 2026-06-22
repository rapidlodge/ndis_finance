frappe.query_reports["NDIS Governed Limited Op Design Item Report"] = {
    filters: [
        {
            fieldname: "design",
            label: __("Design"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Design"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
