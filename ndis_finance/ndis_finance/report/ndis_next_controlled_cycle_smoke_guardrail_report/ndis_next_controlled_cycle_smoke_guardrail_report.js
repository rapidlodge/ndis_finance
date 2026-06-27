frappe.query_reports["NDIS Next Controlled Cycle Smoke Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nSmoke Completed - Rollback Required\nBlocked\nCancelled"
        }
    ]
};
