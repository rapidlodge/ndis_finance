frappe.query_reports["NDIS Limited Production Batch Smoke Rollback Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRolled Back\nBlocked\nCancelled"
        }
    ]
};
