frappe.query_reports["NDIS Runtime Watch Violation Sim Freeze Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nFrozen\nBlocked\nCancelled"
        }
    ]
};
