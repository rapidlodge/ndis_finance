frappe.query_reports["NDIS Claim Cycle Time Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Service From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Service To Date"), fieldtype: "Date" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "funding_source", label: __("Funding Source"), fieldtype: "Link", options: "NDIS Funding Source" },
        { fieldname: "support_item_number", label: __("Support Item Number"), fieldtype: "Data" },
        {
            fieldname: "claim_status",
            label: __("Claim Status"),
            fieldtype: "Select",
            options: "\nDraft\nReady to Claim\nSubmitted\nPaid\nShort Paid\nRejected\nReclaim Required\nInvoice Cancelled\nCancelled",
        },
    ],
};
