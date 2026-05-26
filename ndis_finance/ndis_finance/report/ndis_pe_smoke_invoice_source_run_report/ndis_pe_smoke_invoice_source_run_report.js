frappe.query_reports["NDIS PE Smoke Invoice Source Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Executed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Executed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nNeeds Review\nBlocked\nSource Created\nSource Cancelled\nCancelled"
        }
    ]
};
