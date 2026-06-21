frappe.query_reports["NDIS Governed Limited Op Smoke Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nSmoke Completed - Rollback Required\nBlocked\nCancelled"
        }
    ]
};
