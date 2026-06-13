frappe.query_reports["NDIS Guarded Adapter Final Policy Decision Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nDecision Applied\nBlocked\nCancelled"
        }
    ]
};
