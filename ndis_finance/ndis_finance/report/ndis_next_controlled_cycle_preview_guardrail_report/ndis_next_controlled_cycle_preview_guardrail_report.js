frappe.query_reports["NDIS Next Controlled Cycle Preview Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPreview Approved\nBlocked\nCancelled"
        }
    ]
};
