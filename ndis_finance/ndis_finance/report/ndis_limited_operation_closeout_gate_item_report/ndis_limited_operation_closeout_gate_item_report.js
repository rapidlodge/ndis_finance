frappe.query_reports["NDIS Limited Operation Closeout Gate Item Report"] = {
    filters: [
        {
            fieldname: "closeout",
            label: __("Closeout"),
            fieldtype: "Link",
            options: "NDIS Limited Operation Closeout Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
