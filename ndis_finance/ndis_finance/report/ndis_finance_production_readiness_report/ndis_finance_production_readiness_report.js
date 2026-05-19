frappe.query_reports["NDIS Finance Production Readiness Report"] = {
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
            fieldname: "production_ready_allowed",
            label: __("Production Ready Allowed"),
            fieldtype: "Select",
            options: "\n1\n0"
        }
    ]
};
