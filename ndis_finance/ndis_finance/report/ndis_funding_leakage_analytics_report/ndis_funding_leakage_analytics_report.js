frappe.query_reports["NDIS Funding Leakage Analytics Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Service From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Service To Date"), fieldtype: "Date" },
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: "House\nParticipant\nLeakage Type\nSeverity\nStatus",
            default: "House",
        },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        {
            fieldname: "leakage_type",
            label: __("Leakage Type"),
            fieldtype: "Select",
            options: "\nUnclaimed Shift\nUnderbilling\nOverbilling Risk\nMissing Support Item\nMissing Service Booking\nPlan Expired\nBudget Exhausted\nPayment Shortfall\nRejected Claim\nOther",
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nOpen\nIn Review\nResolved\nWritten Off\nClosed",
        },
        { fieldname: "open_only", label: __("Open Only"), fieldtype: "Check", default: 0 },
    ],
};
