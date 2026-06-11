frappe.query_reports["NDIS Limited Batch Runtime Guard Evidence Item Report"] = {
    filters: [
        {
            fieldname: "evidence_freeze",
            label: __("Evidence Freeze"),
            fieldtype: "Link",
            options: "NDIS Limited Batch Runtime Guard Evidence Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
