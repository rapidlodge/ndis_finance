frappe.query_reports["NDIS Guarded Limited Adapter Smoke Rollback Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRolled Back\nBlocked\nCancelled"
        }
    ]
};
