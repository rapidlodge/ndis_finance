frappe.query_reports["NDIS Next Governed Limited Op Candidate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCandidate Selection Approved\nBlocked\nCancelled"
        }
    ]
};
