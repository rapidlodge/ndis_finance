frappe.query_reports["NDIS PE Production Posting Preview Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Previewed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Previewed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "preview_status",
            label: __("Preview Status"),
            fieldtype: "Select",
            options: "\nReady For Controlled Live Adapter Design\nReady With Warnings\nNeeds Review\nBlocked"
        }
    ]
};
