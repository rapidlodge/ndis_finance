frappe.query_reports["NDIS Next Controlled Cycle Preview Item Report"] = {
    filters: [
        {
            fieldname: "preview",
            label: __("Preview"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Preview"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
