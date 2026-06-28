frappe.query_reports["NDIS Next Post Closeout Steady Baseline Item Report"] = {
    filters: [
        {
            fieldname: "baseline",
            label: __("Baseline"),
            fieldtype: "Link",
            options: "NDIS Next Post Closeout Steady Baseline"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
