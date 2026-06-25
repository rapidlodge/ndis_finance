frappe.query_reports["NDIS Governed Next Op Smoke Item Report"] = {
    filters: [
        {
            fieldname: "smoke",
            label: __("Smoke"),
            fieldtype: "Link",
            options: "NDIS Governed Next Op Smoke"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
