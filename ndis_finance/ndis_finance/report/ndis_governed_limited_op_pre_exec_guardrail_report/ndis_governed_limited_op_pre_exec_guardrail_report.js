frappe.query_reports["NDIS Governed Limited Op Pre Exec Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPre-Execution Approved\nBlocked\nCancelled"
        }
    ]
};
