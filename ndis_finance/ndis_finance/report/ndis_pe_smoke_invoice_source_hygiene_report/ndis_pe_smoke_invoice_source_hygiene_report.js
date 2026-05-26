frappe.query_reports["NDIS PE Smoke Invoice Source Hygiene Report"] = {
    filters: [
        {
            fieldname: "docstatus",
            label: __("Docstatus"),
            fieldtype: "Select",
            options: "\n0\n1\n2"
        },
        {
            fieldname: "outstanding_only",
            label: __("Outstanding Only"),
            fieldtype: "Check",
            default: 1
        }
    ]
};
