frappe.query_reports["NDIS Limited Production Batch Enablement Smoke Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nSource Pending\nNeeds Review\nEnabled - Rollback Required\nBlocked\nCancelled"
        }
    ]
};
