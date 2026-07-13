frappe.query_reports["NDIS Next Governed Limited Op Smoke Rollback Guardrail Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nNeeds Review\nRolled Back\nCancelled"
        }
    ]
};
