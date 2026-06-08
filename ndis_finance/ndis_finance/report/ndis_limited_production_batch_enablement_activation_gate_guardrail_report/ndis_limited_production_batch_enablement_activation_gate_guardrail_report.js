frappe.query_reports["NDIS Limited Production Batch Enablement Activation Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nSource Pending\nNeeds Review\nActivation Allowed\nBlocked\nCancelled"
        }
    ]
};