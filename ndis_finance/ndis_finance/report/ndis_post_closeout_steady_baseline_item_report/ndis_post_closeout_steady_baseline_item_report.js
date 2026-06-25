frappe.query_reports["NDIS Post Closeout Steady Baseline Item Report"] = {
    filters: [
        {
            fieldname: "baseline",
            label: __("Baseline"),
            fieldtype: "Link",
            options: "NDIS Post Closeout Steady Baseline"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
