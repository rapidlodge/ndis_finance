frappe.query_reports["NDIS Post Closeout Steady Baseline Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nBaseline Active\nBlocked\nCancelled"
        }
    ]
};
