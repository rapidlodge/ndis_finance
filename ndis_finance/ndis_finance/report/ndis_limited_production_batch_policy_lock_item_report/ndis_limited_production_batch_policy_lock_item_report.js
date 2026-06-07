frappe.query_reports["NDIS Limited Production Batch Policy Lock Item Report"] = {
    filters: [
        {
            fieldname: "policy_lock",
            label: __("Policy Lock"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Policy Lock"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
