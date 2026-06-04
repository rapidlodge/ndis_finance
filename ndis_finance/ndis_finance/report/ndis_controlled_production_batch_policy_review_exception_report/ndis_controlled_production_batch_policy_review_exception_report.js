frappe.query_reports["NDIS Controlled Production Batch Policy Review Exception Report"] = {
    filters: [
        {
            fieldname: "policy_review_gate",
            label: __("Policy Review Gate"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Policy Review Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
