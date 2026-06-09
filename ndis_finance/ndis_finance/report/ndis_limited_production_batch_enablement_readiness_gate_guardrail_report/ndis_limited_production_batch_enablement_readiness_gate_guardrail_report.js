frappe.query_reports["NDIS Limited Production Batch Enablement Readiness Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nApproved\nBlocked\nCancelled"
        }
    ]
};
