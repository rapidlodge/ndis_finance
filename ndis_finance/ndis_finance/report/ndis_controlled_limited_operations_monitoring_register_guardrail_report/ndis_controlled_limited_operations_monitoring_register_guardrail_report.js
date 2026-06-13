frappe.query_reports["NDIS Controlled Limited Operations Monitoring Register Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nActive\nBlocked\nCancelled"
        }
    ]
};
