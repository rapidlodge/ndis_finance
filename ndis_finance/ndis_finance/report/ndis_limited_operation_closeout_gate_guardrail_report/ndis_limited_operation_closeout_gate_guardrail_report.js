frappe.query_reports["NDIS Limited Operation Closeout Gate Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCloseout Approved\nBlocked\nCancelled"
        }
    ]
};
