frappe.query_reports["NDIS Limited Production Batch Policy Design Item Report"] = {
    filters: [
        {
            fieldname: "policy_design",
            label: __("Policy Design"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Policy Design"
        },
        {
            fieldname: "rule_status",
            label: __("Rule Status"),
            fieldtype: "Select",
            options: "\nDesigned\nBlocked\nCancelled"
        }
    ]
};
