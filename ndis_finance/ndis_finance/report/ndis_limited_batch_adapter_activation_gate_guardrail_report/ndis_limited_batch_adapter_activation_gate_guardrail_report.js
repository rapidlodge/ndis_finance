frappe.query_reports["NDIS Limited Batch Adapter Activation Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nActivation Allowed\nBlocked\nCancelled"
        }
    ]
};
