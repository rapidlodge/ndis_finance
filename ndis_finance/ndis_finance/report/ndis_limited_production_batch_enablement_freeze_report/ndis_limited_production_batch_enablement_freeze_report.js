frappe.query_reports["NDIS Limited Production Batch Enablement Freeze Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nFrozen\nBlocked\nCancelled"
        }
    ]
};
