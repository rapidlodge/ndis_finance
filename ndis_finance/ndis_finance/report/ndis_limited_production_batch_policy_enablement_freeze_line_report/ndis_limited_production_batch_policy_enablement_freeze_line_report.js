frappe.query_reports["NDIS Limited Production Batch Policy Enablement Freeze Line Report"] = {
    filters: [
        {
            fieldname: "evidence_freeze",
            label: __("Evidence Freeze"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Policy Enablement Freeze"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nFrozen\nPreview Only\nBlocked\nCancelled"
        }
    ]
};
