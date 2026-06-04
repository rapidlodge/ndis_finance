frappe.query_reports["NDIS Controlled Production Batch Smoke Evidence Freeze Exception Report"] = {
    filters: [
        {
            fieldname: "evidence_freeze",
            label: __("Evidence Freeze"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Smoke Evidence Freeze"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};