frappe.query_reports["NDIS Next Governed Limited Op Smoke Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCompleted\nSmoke Completed - Rollback Required\nBlocked\nCancelled"
        }
    ]
};
