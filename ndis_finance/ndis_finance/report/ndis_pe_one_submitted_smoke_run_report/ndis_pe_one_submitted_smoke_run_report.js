frappe.query_reports["NDIS PE One Submitted Smoke Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Executed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Executed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nNeeds Review\nBlocked\nSubmitted\nPayment Cancelled\nCancelled"
        }
    ]
};
