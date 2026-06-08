frappe.query_reports["NDIS Limited Production Batch Enablement Preview Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPreviewed\nBlocked\nCancelled"
        }
    ]
};
