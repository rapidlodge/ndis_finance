frappe.query_reports["NDIS Controlled Production Batch Activation Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nNeeds Review\nActivation Allowed\nBlocked\nCancelled"
        }
    ]
};
