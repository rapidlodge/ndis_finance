frappe.query_reports["NDIS Payroll Cost by Participant Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Period From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Period To Date"), fieldtype: "Date" },
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        { fieldname: "au_payroll_run_log", label: __("AU Payroll Run Log"), fieldtype: "Link", options: "AU Payroll Run Log" },
        { fieldname: "payroll_cost_import", label: __("Payroll Cost Import"), fieldtype: "Link", options: "NDIS Payroll Cost Import" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" },
    ],
};
