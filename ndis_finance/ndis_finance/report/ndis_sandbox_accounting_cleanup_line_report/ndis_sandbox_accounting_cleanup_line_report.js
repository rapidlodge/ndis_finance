frappe.query_reports["NDIS Sandbox Accounting Cleanup Line Report"] = {
    filters: [
        {
            fieldname: "cleanup_pack",
            label: __("Cleanup Pack"),
            fieldtype: "Link",
            options: "NDIS Sandbox Accounting Cleanup Pack"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nCandidate\nEligible\nDeleted\nCancelled\nBlocked\nWarning\nInfo"
        },
        {
            fieldname: "record_doctype",
            label: __("Record Type"),
            fieldtype: "Select",
            options: "\nPayment Entry\nSales Invoice"
        },
        { fieldname: "action_type", label: __("Action Type"), fieldtype: "Data" }
    ]
};
