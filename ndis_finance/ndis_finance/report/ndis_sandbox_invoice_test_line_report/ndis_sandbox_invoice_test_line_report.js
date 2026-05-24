frappe.query_reports["NDIS Sandbox Invoice Test Line Report"] = {
    filters: [
        {
            fieldname: "test_run",
            label: __("Test Run"),
            fieldtype: "Link",
            options: "NDIS Sandbox Invoice Test Run"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nCreated\nReused\nSubmitted\nBlocked\nCancelled"
        },
        {
            fieldname: "record_doctype",
            label: __("Record DocType"),
            fieldtype: "Select",
            options: "\nCustomer\nItem\nSales Invoice"
        }
    ]
};
