frappe.query_reports["NDIS Payroll Cost by House Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Period From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Period To Date"), fieldtype: "Date" },
        { fieldname: "au_payroll_run_log", label: __("AU Payroll Run Log"), fieldtype: "Link", options: "AU Payroll Run Log" },
        { fieldname: "payroll_cost_import", label: __("Payroll Cost Import"), fieldtype: "Link", options: "NDIS Payroll Cost Import" },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
        {
            fieldname: "line_status",
            label: __("Line Status"),
            fieldtype: "Select",
            options: "\nImported\nMapped\nUnmapped\nCost Pool Created\nAllocated\nSkipped\nCancelled\nError",
        },
    ],
};
