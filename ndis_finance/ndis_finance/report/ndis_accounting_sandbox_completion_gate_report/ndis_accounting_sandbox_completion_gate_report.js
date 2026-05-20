frappe.query_reports["NDIS Accounting Sandbox Completion Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPassed\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "completion_status",
            label: __("Completion Status"),
            fieldtype: "Select",
            options: "\nComplete\nWatch\nNeeds Cleanup\nBlocked"
        }
    ]
};
