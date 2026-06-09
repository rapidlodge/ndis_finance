frappe.query_reports["NDIS Limited Production Batch Policy Enablement Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nEnabled - Final Rollback Optional\nBlocked\nCancelled"
        }
    ]
};
