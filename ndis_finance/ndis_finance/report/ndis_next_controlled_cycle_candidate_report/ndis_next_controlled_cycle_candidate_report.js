frappe.query_reports["NDIS Next Controlled Cycle Candidate Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCandidate Selection Approved\nBlocked\nCancelled"
        }
    ]
};
