frappe.query_reports["NDIS Next Governed Limited Op Rollback Freeze Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nFreeze Completed\nBlocked\nCancelled"
        }
    ]
};
