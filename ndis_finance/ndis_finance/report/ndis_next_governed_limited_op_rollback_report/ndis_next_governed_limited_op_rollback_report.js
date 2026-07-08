frappe.query_reports["NDIS Next Governed Limited Op Rollback Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRollback Completed\nRolled Back\nBlocked\nCancelled"
        }
    ]
};
