frappe.query_reports["NDIS Payment Entry Allocation Preview Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Created From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Created To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "validation_status",
            label: __("Validation Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocked"
        },
        {
            fieldname: "mapping_rule",
            label: __("Mapping Rule"),
            fieldtype: "Link",
            options: "NDIS Payment Entry Mapping Rule"
        },
        {
            fieldname: "remittance_import",
            label: __("Remittance Import"),
            fieldtype: "Link",
            options: "NDIS Remittance Import"
        }
    ]
};
