frappe.query_reports["NDIS Controlled Production Batch Smoke Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nSubmitted - Rollback Required\nFailed\nCancelled"
        }
    ]
};
