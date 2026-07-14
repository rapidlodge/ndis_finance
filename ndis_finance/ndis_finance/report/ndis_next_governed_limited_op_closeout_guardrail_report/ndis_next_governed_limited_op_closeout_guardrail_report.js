frappe.query_reports["NDIS Next Governed Limited Op Closeout Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nClosed\nBlocked\nCancelled\nCloseout Approved"
        }
    ]
};
