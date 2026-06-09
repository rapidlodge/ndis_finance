frappe.query_reports["NDIS Limited Production Batch Enablement Readiness Gate Item Report"] = {
    filters: [
        {
            fieldname: "readiness_gate",
            label: __("Readiness Gate"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Readiness Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
