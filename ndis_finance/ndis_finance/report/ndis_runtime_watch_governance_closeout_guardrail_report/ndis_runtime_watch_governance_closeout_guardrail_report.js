frappe.query_reports["NDIS Runtime Watch Governance Closeout Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nGovernance Closeout Approved\nBlocked\nCancelled"
        }
    ]
};
