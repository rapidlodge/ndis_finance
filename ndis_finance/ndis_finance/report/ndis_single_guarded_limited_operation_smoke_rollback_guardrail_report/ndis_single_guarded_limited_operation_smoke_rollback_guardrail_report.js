frappe.query_reports["NDIS Single Guarded Limited Operation Smoke Rollback Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRollback Completed\nBlocked\nCancelled"
        }
    ]
};