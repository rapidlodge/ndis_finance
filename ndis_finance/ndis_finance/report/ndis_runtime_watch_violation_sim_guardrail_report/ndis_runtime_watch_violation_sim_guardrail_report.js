frappe.query_reports["NDIS Runtime Watch Violation Sim Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nSimulation Completed\nBlocked\nCancelled"
        }
    ]
};
