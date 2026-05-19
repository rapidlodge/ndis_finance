frappe.query_reports["NDIS Profitability Executive Dashboard"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
        { fieldname: "funding_source", label: __("Funding Source"), fieldtype: "Link", options: "NDIS Funding Source" },
        {
            fieldname: "cost_type",
            label: __("Cost Type"),
            fieldtype: "Select",
            options: "\nPayroll\nRent\nUtilities\nFood\nTransport\nTravel\nTraining\nInsurance\nMaintenance\nAdministration\nNon-Billable Support\nOther"
        }
    ]
};
