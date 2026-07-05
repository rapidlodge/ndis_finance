frappe.query_reports["NDIS Next Governed Limited Op Planning Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPlanning Approved\nBlocked\nCancelled"
        }
    ]
};
