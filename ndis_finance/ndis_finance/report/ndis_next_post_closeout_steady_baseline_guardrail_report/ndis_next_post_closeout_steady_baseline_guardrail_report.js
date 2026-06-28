frappe.query_reports["NDIS Next Post Closeout Steady Baseline Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nBaseline Active\nBlocked\nCancelled"
        }
    ]
};
