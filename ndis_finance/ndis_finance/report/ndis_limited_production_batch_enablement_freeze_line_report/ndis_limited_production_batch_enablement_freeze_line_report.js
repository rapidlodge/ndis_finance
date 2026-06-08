frappe.query_reports["NDIS Limited Production Batch Enablement Freeze Line Report"] = {
    filters: [
        {
            fieldname: "evidence_freeze",
            label: __("Evidence Freeze"),
            fieldtype: "Link",
            options: "NDIS Limited Production Batch Enablement Evidence Freeze"
        },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nFrozen\nPreview Only\nBlocked\nCancelled"
        }
    ]
};
