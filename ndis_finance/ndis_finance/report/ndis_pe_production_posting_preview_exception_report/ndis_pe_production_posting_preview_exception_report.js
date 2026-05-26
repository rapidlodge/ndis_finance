frappe.query_reports["NDIS PE Production Posting Preview Exception Report"] = {
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
            options: "\nBlocked\nDuplicate\nWarning"
        },
        {
            fieldname: "event_type",
            label: __("Event Type"),
            fieldtype: "Select",
            options: "\nPaid Claim\nShort Paid Claim\nRejected Claim"
        }
    ]
};
