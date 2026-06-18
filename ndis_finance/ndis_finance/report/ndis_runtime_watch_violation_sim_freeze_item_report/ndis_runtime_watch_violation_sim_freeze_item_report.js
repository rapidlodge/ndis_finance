frappe.query_reports["NDIS Runtime Watch Violation Sim Freeze Item Report"] = {
    filters: [
        {
            fieldname: "freeze",
            label: __("Freeze"),
            fieldtype: "Link",
            options: "NDIS Runtime Watch Violation Sim Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
