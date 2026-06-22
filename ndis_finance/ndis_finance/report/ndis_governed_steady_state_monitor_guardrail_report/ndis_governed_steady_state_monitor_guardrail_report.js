frappe.query_reports["NDIS Governed Steady State Monitor Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nMonitor Active\nBlocked\nCancelled"
        }
    ]
};
