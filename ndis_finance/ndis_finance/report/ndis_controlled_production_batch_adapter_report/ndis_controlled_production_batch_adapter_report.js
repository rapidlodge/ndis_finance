frappe.query_reports["NDIS Controlled Production Batch Adapter Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nHard Blocked\nBlocked\nCancelled"
        }
    ]
};
