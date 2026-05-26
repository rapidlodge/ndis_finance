frappe.query_reports["NDIS PE Single Record Draft Smoke Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Executed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Executed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nSource Pending\nDraft Created\nSubmit Block Verified\nCleaned\nNeeds Review\nBlocked\nCancelled"
        }
    ]
};
