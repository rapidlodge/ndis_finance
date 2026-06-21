frappe.query_reports["NDIS Governed Steady State Baseline Item Report"] = {
    filters: [
        {
            fieldname: "baseline",
            label: __("Baseline"),
            fieldtype: "Link",
            options: "NDIS Governed Steady State Baseline"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
