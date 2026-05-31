frappe.query_reports["NDIS Real Remittance PE Adapter Exception Report"] = {
    filters: [
        {
            fieldname: "adapter_run",
            label: __("Adapter Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Adapter Run"
        },
        {
            fieldname: "adapter_status",
            label: __("Adapter Status"),
            fieldtype: "Select",
            default: "Validation Blocked",
            options: "\nValidation Blocked\nReview Blocked\nHard Blocked\nSource Pending\nCancelled"
        }
    ]
};
