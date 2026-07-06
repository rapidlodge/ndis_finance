frappe.query_reports["NDIS Next Governed Limited Op Rollback Freeze Item Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nFrozen\nBlocked\nCancelled"
        }
    ]
};
