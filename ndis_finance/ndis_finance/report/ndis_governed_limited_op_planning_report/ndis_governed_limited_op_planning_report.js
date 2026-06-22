frappe.query_reports["NDIS Governed Limited Op Planning Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPlanning Approved\nBlocked\nCancelled"
        }
    ]
};
