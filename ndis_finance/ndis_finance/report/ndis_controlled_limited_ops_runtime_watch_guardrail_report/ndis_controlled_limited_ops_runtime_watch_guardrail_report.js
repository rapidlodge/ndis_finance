frappe.query_reports["NDIS Controlled Limited Ops Runtime Watch Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nWatch Active\nBlocked\nCancelled"
        }
    ]
};
