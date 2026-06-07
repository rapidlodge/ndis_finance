frappe.query_reports["NDIS Limited Production Batch Enablement Design Gate Item Report"] = {
    filters: [
        {
            fieldname: "enablement_gate",
            label: __("Enablement Gate"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Design Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
