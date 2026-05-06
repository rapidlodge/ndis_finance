frappe.query_reports["NDIS Claim Exception Report"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("Service From Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: __("Service To Date"),
            fieldtype: "Date"
        },
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
            fieldname: "claim_status",
            label: __("Claim Status"),
            fieldtype: "Select",
            options: "\nShort Paid\nRejected\nReclaim Required"
        }
    ]
};
