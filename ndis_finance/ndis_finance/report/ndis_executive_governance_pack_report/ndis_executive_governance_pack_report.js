frappe.query_reports["NDIS Executive Governance Pack Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Pack From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Pack To Date"), fieldtype: "Date" },
        {
            fieldname: "pack_type",
            label: __("Pack Type"),
            fieldtype: "Select",
            options: "\nManual\nMonthly\nBoard\nInternal Review"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nGenerated\nSigned Off\nCancelled\nFailed"
        },
        {
            fieldname: "governance_status",
            label: __("Governance Status"),
            fieldtype: "Select",
            options: "\nStrong\nWatch\nNeeds Attention\nCritical"
        }
    ]
};
