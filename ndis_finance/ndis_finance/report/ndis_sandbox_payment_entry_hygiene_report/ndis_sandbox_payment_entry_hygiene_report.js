frappe.query_reports["NDIS Sandbox Payment Entry Hygiene Report"] = {
    filters: [
        {
            fieldname: "docstatus",
            label: __("Docstatus"),
            fieldtype: "Select",
            options: "\n0\n1\n2"
        },
        {
            fieldname: "sandbox_run",
            label: __("Sandbox Run"),
            fieldtype: "Link",
            options: "NDIS Sandbox Payment Entry Run"
        },
        {
            fieldname: "min_age_days",
            label: __("Minimum Age Days"),
            fieldtype: "Int"
        }
    ]
};
