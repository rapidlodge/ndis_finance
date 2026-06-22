frappe.query_reports["NDIS Governed Limited Op Precheck Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPrecheck Approved\nBlocked\nCancelled"
        }
    ]
};
