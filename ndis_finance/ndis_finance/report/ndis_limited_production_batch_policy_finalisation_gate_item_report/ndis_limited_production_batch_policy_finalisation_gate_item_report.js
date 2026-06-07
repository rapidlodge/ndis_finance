frappe.query_reports["NDIS Limited Production Batch Policy Finalisation Gate Item Report"] = {
    filters: [
        {
            fieldname: "finalisation_gate",
            label: __("Finalisation Gate"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Policy Finalisation Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};