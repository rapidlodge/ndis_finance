frappe.query_reports["NDIS PE Production Adapter Run Line Report"] = {
    filters: [
        {
            fieldname: "adapter_run",
            label: __("Adapter Run"),
            fieldtype: "Link",
            options: "NDIS PE Production Adapter Run"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nHard Blocked\nValidation Blocked\nDuplicate Blocked\nRejected Blocked\nWarning\nInfo\nCancelled"
        },
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nPaid Claim\nShort Paid Claim\nRejected Claim"
        }
    ]
};
