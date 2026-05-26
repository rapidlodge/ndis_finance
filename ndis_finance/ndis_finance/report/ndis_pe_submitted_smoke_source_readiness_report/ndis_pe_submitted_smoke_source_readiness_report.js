frappe.query_reports["NDIS PE Submitted Smoke Source Readiness Report"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: "CONNECTUS HOME CARE PTY LTD"
        },
        {
            fieldname: "only_outstanding",
            label: __("Outstanding Only"),
            fieldtype: "Check",
            default: 1
        }
    ]
};
