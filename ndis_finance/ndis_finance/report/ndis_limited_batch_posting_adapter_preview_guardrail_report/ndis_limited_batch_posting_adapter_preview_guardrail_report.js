frappe.query_reports["NDIS Limited Batch Posting Adapter Preview Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPreviewed\nBlocked\nCancelled"
        }
    ]
};
