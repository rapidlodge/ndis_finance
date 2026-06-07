frappe.query_reports["NDIS Limited Production Batch Adapter Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nHard Blocked\nBlocked\nCancelled"
        }
    ]
};
