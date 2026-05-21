frappe.query_reports["NDIS Sandbox Payment Entry Run Line Report"] = {
    filters: [
        {
            fieldname: "sandbox_run",
            label: __("Sandbox Run"),
            fieldtype: "Link",
            options: "NDIS Sandbox Payment Entry Run"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nIncluded In Draft PE\nExcluded\nDuplicate\nBlocked\nCancelled"
        },
        {
            fieldname: "sales_invoice",
            label: __("Sales Invoice"),
            fieldtype: "Link",
            options: "Sales Invoice"
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer"
        }
    ]
};
