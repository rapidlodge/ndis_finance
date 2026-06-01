frappe.query_reports["NDIS Real Remittance Batch Policy Register Report"] = {
    filters: [
        {
            fieldname: "policy_status",
            label: __("Policy Status"),
            fieldtype: "Select",
            options: "\nDraft\nActive\nRetired"
        },
        {
            fieldname: "policy_category",
            label: __("Policy Category"),
            fieldtype: "Data"
        },
        {
            fieldname: "batch_live_enabled",
            label: __("Batch Live Enabled"),
            fieldtype: "Select",
            options: "\n0\n1"
        }
    ]
};
