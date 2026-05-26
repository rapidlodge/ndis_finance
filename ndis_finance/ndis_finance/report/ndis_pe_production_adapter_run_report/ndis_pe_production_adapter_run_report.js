frappe.query_reports["NDIS PE Production Adapter Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Executed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Executed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nHard Blocked\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "adapter_status",
            label: __("Adapter Status"),
            fieldtype: "Select",
            options: "\nReady For Activation Gate Design\nReady With Warnings\nNeeds Review\nBlocked"
        }
    ]
};
