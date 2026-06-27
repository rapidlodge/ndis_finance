frappe.query_reports["NDIS Next Controlled Cycle Cand Valid Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCandidate Validation Approved\nBlocked\nCancelled"
        }
    ]
};
