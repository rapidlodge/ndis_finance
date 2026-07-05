frappe.query_reports["NDIS Next Governed Limited Op Design Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nDesign Approved\nBlocked\nCancelled"
        }
    ]
};
