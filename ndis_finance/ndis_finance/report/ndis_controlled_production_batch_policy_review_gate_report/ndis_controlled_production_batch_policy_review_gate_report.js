frappe.query_reports["NDIS Controlled Production Batch Policy Review Gate Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nApproved For Limited Policy Design\nBlocked\nCancelled"
        }
    ]
};
