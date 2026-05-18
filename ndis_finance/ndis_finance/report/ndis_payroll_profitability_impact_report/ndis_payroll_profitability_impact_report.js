frappe.query_reports["NDIS Payroll Profitability Impact Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Period From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Period To Date"), fieldtype: "Date" },
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
    ],
};
