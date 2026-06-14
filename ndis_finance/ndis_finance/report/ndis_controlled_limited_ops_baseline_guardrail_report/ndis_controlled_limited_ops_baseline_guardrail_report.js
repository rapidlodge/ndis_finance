frappe.query_reports["NDIS Controlled Limited Ops Baseline Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nBaseline Active\nBlocked\nCancelled"
        }
    ]
};
