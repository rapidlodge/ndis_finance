frappe.query_reports["NDIS Next Governed Limited Op Exec Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nExecution Gate Approved\nBlocked\nCancelled"
        }
    ]
};
