frappe.query_reports["NDIS True House Profitability Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Service From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Service To Date"), fieldtype: "Date" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
        { fieldname: "funding_source", label: __("Funding Source"), fieldtype: "Link", options: "NDIS Funding Source" },
        { fieldname: "support_item_number", label: __("Support Item Number"), fieldtype: "Data" },
        {
            fieldname: "claim_status",
            label: __("Claim Status"),
            fieldtype: "Select",
            options: "\nDraft\nReady to Claim\nSubmitted\nPaid\nShort Paid\nRejected\nReclaim Required\nInvoice Cancelled\nCancelled",
        },
        {
            fieldname: "cost_type",
            label: __("Cost Type"),
            fieldtype: "Select",
            options: "\nPayroll\nRent\nUtilities\nFood\nTransport\nTravel\nTraining\nInsurance\nMaintenance\nAdministration\nNon-Billable Support\nOther",
        },
        {
            fieldname: "allocation_method",
            label: __("Allocation Method"),
            fieldtype: "Select",
            options: "\nEqual Participant Split\nClaim Amount Share\nPaid Amount Share\nDirect Participant\nHouse Only",
        },
    ],
};
