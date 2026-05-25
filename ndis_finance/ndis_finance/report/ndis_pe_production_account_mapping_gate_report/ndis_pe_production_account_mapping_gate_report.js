frappe.query_reports["NDIS PE Production Account Mapping Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nHardened\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "hardening_status",
            label: __("Hardening Status"),
            fieldtype: "Select",
            options: "\nReady For Production Posting Preview\nReady With Warnings\nNeeds Review\nBlocked"
        }
    ]
};
