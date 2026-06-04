frappe.query_reports["NDIS Limited Production Batch Policy Design Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nDesigned\nBlocked\nCancelled"
        }
    ]
};
