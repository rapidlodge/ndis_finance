frappe.query_reports["NDIS Controlled Production Batch Smoke Rollback Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRolled Back\nFailed\nCancelled"
        }
    ]
};