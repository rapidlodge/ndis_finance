frappe.query_reports["NDIS Limited Production Batch Policy Lock Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nLocked\nBlocked\nCancelled"
        }
    ]
};
