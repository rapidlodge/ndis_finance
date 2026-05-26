frappe.query_reports["NDIS PE Production Activation Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nActivation Allowed\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "activation_status",
            label: __("Activation Status"),
            fieldtype: "Select",
            options: "\nReady For Single-record Live Smoke\nReady With Warnings\nNeeds Review\nBlocked"
        }
    ]
};
