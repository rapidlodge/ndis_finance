frappe.query_reports["NDIS Limited Production Batch Use Monitor Gate Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nApproved\nBlocked\nCancelled"
        }
    ]
};
