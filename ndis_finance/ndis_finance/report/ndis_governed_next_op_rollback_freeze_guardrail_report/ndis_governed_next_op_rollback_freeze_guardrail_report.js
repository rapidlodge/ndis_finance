frappe.query_reports["NDIS Governed Next Op Rollback Freeze Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nFrozen\nBlocked\nCancelled"
        }
    ]
};
