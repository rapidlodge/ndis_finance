frappe.query_reports["NDIS Next Controlled Cycle Rollback Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRollback Completed\nBlocked\nCancelled"
        }
    ]
};
