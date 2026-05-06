frappe.query_reports["NDIS CFO Exception Dashboard"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
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
            fieldname: "case_type",
            label: __("Case Type"),
            fieldtype: "Select",
            options: "\nPayment Shortfall\nRejected Claim\nPlan Manager Follow Up\nNDIA Follow Up\nSelf Managed Follow Up\nInvoice Overdue\nRemittance Request\nInvoice Resend\nWrite Off Review\nOther"
        },
        {
            fieldname: "overdue_only",
            label: __("Overdue Only"),
            fieldtype: "Check",
            default: 0
        }
    ]
};
