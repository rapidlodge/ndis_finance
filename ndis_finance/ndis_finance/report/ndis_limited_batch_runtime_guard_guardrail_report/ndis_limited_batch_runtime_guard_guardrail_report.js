frappe.query_reports["NDIS Limited Batch Runtime Guard Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nGuarded\nBlocked\nCancelled"
        }
    ]
};
