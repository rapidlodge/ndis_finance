frappe.query_reports["NDIS Recovery Ageing Report"] = {
    filters: [
        {
            fieldname: "participant",
            label: __("Participant"),
            fieldtype: "Link",
            options: "Customer"
        },
        {
            fieldname: "funding_source",
            label: __("Funding Source"),
            fieldtype: "Link",
            options: "NDIS Funding Source"
        },
        {
            fieldname: "house",
            label: __("House"),
            fieldtype: "Link",
            options: "NDIS House"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nOpen\nIn Follow Up\nWaiting For Response\nEscalated\nResolved\nWritten Off\nClosed"
        },
        {
            fieldname: "overdue_only",
            label: __("Overdue Only"),
            fieldtype: "Check",
            default: 0
        }
    ]
};
