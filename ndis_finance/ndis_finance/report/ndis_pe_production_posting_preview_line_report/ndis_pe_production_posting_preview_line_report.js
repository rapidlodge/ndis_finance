frappe.query_reports["NDIS PE Production Posting Preview Line Report"] = {
    filters: [
        {
            fieldname: "posting_preview",
            label: __("Posting Preview"),
            fieldtype: "Link",
            options: "NDIS PE Production Posting Preview"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPreview Eligible\nBlocked\nDuplicate\nWarning\nInfo\nCancelled"
        },
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nPaid Claim\nShort Paid Claim\nRejected Claim"
        },
        {
            fieldname: "claim_outcome",
            label: __("Claim Outcome"),
            fieldtype: "Select",
            options: "\nPaid\nShort Paid\nRejected"
        }
    ]
};
