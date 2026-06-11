frappe.query_reports["NDIS Limited Batch Adapter Activation Gate Item Report"] = {
    filters: [
        {
            fieldname: "activation_gate",
            label: __("Activation Gate"),
            fieldtype: "Link",
            options: "NDIS Limited Batch Adapter Activation Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
