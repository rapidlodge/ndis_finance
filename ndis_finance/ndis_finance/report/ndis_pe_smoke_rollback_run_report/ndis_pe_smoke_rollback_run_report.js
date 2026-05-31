frappe.query_reports["NDIS PE Smoke Rollback Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Executed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Executed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nNeeds Review\nBlocked\nPayment Entry Cancelled\nFully Rolled Back\nCancelled"
        }
    ]
};
