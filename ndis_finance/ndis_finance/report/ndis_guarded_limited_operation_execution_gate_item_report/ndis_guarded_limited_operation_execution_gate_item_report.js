frappe.query_reports["NDIS Guarded Limited Operation Execution Gate Item Report"] = {
    filters: [
        {
            fieldname: "gate",
            label: __("Gate"),
            fieldtype: "Link",
            options: "NDIS Guarded Limited Operation Execution Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};