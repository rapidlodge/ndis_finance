frappe.query_reports["NDIS Next Controlled Cycle Planning Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPlanning Approved\nBlocked\nCancelled"
        }
    ]
};
