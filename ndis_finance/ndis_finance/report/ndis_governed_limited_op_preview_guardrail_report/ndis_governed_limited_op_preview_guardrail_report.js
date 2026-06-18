frappe.query_reports["NDIS Governed Limited Op Preview Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPreviewed\nBlocked\nCancelled"
        }
    ]
};
