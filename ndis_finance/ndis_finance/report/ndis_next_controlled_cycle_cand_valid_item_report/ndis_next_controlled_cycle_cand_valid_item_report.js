frappe.query_reports["NDIS Next Controlled Cycle Cand Valid Item Report"] = {
    filters: [
        {
            fieldname: "validation",
            label: __("Validation"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Cand Valid"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
