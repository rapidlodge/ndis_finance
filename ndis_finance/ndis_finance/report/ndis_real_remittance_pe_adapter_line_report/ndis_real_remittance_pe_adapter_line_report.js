frappe.query_reports["NDIS Real Remittance PE Adapter Line Report"] = {
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
            options: "\nHard Blocked\nValidation Blocked\nReview Blocked\nSource Pending\nCancelled"
        },
        {
            fieldname: "adapter_decision",
            label: __("Adapter Decision"),
            fieldtype: "Select",
            options: "\nWould Create PE - Hard Blocked\nValidation Blocked\nReview Blocked\nSource Pending\nCancelled"
        }
    ]
};
