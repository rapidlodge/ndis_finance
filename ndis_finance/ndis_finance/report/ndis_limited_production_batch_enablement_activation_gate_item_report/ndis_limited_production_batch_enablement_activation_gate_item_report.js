frappe.query_reports["NDIS Limited Production Batch Enablement Activation Gate Item Report"] = {
    filters: [
        {
            fieldname: "activation_gate",
            label: __("Activation Gate"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Activation Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};