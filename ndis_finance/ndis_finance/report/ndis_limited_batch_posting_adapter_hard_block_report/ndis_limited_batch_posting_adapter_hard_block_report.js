frappe.query_reports["NDIS Limited Batch Posting Adapter Hard Block Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nHard Blocked\nBlocked\nCancelled"
        }
    ]
};
