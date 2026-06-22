frappe.query_reports["NDIS Governed Limited Op Planning Item Report"] = {
    filters: [
        {
            fieldname: "planning",
            label: __("Planning"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Planning"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
