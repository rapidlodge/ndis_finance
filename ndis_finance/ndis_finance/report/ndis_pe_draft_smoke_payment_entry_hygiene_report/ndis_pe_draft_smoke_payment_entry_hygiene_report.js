frappe.query_reports["NDIS PE Draft Smoke Payment Entry Hygiene Report"] = {
    filters: [
        {
            fieldname: "docstatus",
            label: __("Docstatus"),
            fieldtype: "Select",
            options: "\n0\n1\n2"
        },
        {
            fieldname: "cleanup_required",
            label: __("Cleanup Required Only"),
            fieldtype: "Check"
        }
    ]
};
