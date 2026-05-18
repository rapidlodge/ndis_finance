frappe.query_reports["NDIS Payroll Cost Import Reconciliation Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Period From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Period To Date"), fieldtype: "Date" },
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
        { fieldname: "au_payroll_run_log", label: __("AU Payroll Run Log"), fieldtype: "Link", options: "AU Payroll Run Log" },
        { fieldname: "payroll_cost_import", label: __("Payroll Cost Import"), fieldtype: "Link", options: "NDIS Payroll Cost Import" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nImported\nAllocated\nPartially Allocated\nCancelled\nFailed",
        },
    ],
};
