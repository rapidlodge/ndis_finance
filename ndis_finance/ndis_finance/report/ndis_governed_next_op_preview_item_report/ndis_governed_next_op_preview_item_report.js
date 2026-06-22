frappe.query_reports["NDIS Governed Next Op Preview Item Report"] = {
    filters: [
        {
            fieldname: "preview",
            label: __("Preview"),
            fieldtype: "Link",
            options: "NDIS Governed Next Op Preview"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
