frappe.query_reports["NDIS Limited Production Batch Activation Gate Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nActivation Allowed\nBlocked\nCancelled"
        }
    ]
};
