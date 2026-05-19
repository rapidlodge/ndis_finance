frappe.query_reports["NDIS Executive Exception Register Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Snapshot From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Snapshot To Date"), fieldtype: "Date" },
        { fieldname: "snapshot", label: __("Snapshot"), fieldtype: "Link", options: "NDIS Executive Dashboard Snapshot" },
        { fieldname: "rule", label: __("Rule"), fieldtype: "Link", options: "NDIS Executive Exception Rule" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nOpen\nIn Review\nResolved\nCancelled"
        },
        {
            fieldname: "severity",
            label: __("Severity"),
            fieldtype: "Select",
            options: "\nLow\nMedium\nHigh\nCritical"
        }
    ]
};
