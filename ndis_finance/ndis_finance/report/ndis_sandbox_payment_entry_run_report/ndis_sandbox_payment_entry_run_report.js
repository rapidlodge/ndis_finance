frappe.query_reports["NDIS Sandbox Payment Entry Run Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nValidated\nCreated Draft Payment Entry\nBlocked\nCancelled\nFailed"
        },
        {
            fieldname: "allocation_preview",
            label: __("Allocation Preview"),
            fieldtype: "Link",
            options: "NDIS Payment Entry Allocation Preview"
        },
        {
            fieldname: "payment_entry",
            label: __("Draft Payment Entry"),
            fieldtype: "Link",
            options: "Payment Entry"
        }
    ]
};
