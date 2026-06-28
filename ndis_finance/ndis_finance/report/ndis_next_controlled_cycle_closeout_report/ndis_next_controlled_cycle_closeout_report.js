frappe.query_reports["NDIS Next Controlled Cycle Closeout Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nCloseout Approved\nBlocked\nCancelled"
        }
    ]
};
