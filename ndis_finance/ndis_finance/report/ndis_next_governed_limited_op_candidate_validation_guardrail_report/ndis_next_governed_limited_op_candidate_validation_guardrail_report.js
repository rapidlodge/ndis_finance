frappe.query_reports["NDIS Next Governed Limited Op Candidate Validation Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCandidate Validation Approved\nBlocked\nCancelled"
        }
    ]
};
