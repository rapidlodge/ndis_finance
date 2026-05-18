frappe.query_reports["NDIS Cost Type Analysis Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Period From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Period To Date"), fieldtype: "Date" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
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
