frappe.query_reports["NDIS Governed Limited Ops Readiness Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nReadiness Approved\nBlocked\nCancelled"
        }
    ]
};
