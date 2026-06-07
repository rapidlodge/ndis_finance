frappe.query_reports["NDIS Limited Production Batch Policy Finalisation Gate Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nApproved\nBlocked\nCancelled"
        }
    ]
};