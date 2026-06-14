frappe.query_reports["NDIS Single Guarded Limited Operation Smoke Item Report"] = {
    filters: [
        {
            fieldname: "smoke",
            label: __("Smoke"),
            fieldtype: "Link",
            options: "NDIS Single Guarded Limited Operation Smoke"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};