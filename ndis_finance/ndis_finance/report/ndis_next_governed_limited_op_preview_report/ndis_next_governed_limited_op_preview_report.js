frappe.query_reports["NDIS Next Governed Limited Op Preview Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nPreview Approved\nBlocked\nCancelled"
        }
    ]
};
