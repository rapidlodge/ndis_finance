frappe.query_reports["NDIS Guarded Limited Operation Execution Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nExecution Allowed\nBlocked\nCancelled"
        }
    ]
};