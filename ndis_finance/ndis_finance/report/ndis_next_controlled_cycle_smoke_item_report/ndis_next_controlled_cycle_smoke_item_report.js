frappe.query_reports["NDIS Next Controlled Cycle Smoke Item Report"] = {
    filters: [
        {
            fieldname: "smoke",
            label: __("Smoke"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Smoke"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
