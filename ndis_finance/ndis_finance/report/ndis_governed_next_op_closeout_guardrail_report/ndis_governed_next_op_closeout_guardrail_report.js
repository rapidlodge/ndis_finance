frappe.query_reports["NDIS Governed Next Op Closeout Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCloseout Approved\nBlocked\nCancelled"
        }
    ]
};
