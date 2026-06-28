frappe.query_reports["NDIS Next Post Closeout Runtime Monitor Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nMonitor Active\nBlocked\nCancelled"
        }
    ]
};
