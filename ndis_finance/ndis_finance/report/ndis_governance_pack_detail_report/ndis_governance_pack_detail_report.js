frappe.query_reports["NDIS Governance Pack Detail Report"] = {
    filters: [
        { fieldname: "governance_pack", label: __("Governance Pack"), fieldtype: "Link", options: "NDIS Executive Governance Pack" },
        { fieldname: "from_date", label: __("Pack From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Pack To Date"), fieldtype: "Date" },
        {
            fieldname: "section",
            label: __("Section"),
            fieldtype: "Select",
            options: "\nExecutive KPI\nException Alerts\nAction Plans\nTrend Summary"
        },
        {
            fieldname: "risk_status",
            label: __("Risk Status"),
            fieldtype: "Select",
            options: "\nGood\nInfo\nWatch\nRisk\nCritical"
        }
    ]
};
