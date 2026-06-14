frappe.query_reports["NDIS Controlled Limited Ops Baseline Item Report"] = {
    filters: [
        {
            fieldname: "baseline",
            label: __("Baseline"),
            fieldtype: "Link",
            options: "NDIS Controlled Limited Ops Baseline"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
