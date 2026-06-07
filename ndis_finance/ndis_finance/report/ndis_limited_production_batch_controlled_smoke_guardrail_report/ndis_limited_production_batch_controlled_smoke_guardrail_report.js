frappe.query_reports["NDIS Limited Production Batch Controlled Smoke Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nSubmitted - Rollback Required\nBlocked\nCancelled"
        }
    ]
};
