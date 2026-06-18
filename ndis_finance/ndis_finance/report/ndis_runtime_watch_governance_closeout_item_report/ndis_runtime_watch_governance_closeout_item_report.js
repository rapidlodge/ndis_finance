frappe.query_reports["NDIS Runtime Watch Governance Closeout Item Report"] = {
    filters: [
        {
            fieldname: "governance_closeout",
            label: __("Governance Closeout"),
            fieldtype: "Link",
            options: "NDIS Runtime Watch Governance Closeout"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
