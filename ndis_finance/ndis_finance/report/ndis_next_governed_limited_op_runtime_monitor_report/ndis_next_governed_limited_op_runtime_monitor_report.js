frappe.query_reports["NDIS Next Governed Limited Op Runtime Monitor Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nRuntime Monitor Active\nMonitor Active\nBlocked\nCancelled"
        }
    ]
};
