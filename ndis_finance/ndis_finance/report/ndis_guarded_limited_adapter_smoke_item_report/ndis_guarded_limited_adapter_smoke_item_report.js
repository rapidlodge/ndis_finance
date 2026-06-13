frappe.query_reports["NDIS Guarded Limited Adapter Smoke Item Report"] = {
    filters: [
        {
            fieldname: "smoke",
            label: __("Smoke"),
            fieldtype: "Link",
            options: "NDIS Guarded Limited Adapter Smoke"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
