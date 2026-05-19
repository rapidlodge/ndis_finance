frappe.query_reports["NDIS Executive Snapshot Detail Report"] = {
    filters: [
        { fieldname: "snapshot", label: __("Snapshot"), fieldtype: "Link", options: "NDIS Executive Dashboard Snapshot" },
        { fieldname: "from_date", label: __("Snapshot From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Snapshot To Date"), fieldtype: "Date" },
        {
            fieldname: "section",
            label: __("Section"),
            fieldtype: "Select",
            options: "\nRevenue\nCost\nMargin\nLeakage\nRecovery\nPayroll\nAutomation\nWorst Houses\nWorst Participants"
        },
        {
            fieldname: "risk_status",
            label: __("Risk Status"),
            fieldtype: "Select",
            options: "\nGood\nInfo\nWatch\nRisk"
        }
    ]
};
