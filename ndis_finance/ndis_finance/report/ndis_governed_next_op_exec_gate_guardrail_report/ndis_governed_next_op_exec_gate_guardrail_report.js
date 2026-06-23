frappe.query_reports["NDIS Governed Next Op Exec Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nExecution Gate Approved\nBlocked\nCancelled"
        }
    ]
};
