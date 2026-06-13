frappe.query_reports["NDIS Controlled Limited Operation Pre Check Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nApproved\nBlocked\nCancelled"
        }
    ]
};