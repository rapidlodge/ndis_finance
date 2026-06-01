frappe.query_reports["NDIS Real Remittance PE Source Harness Line Report"] = {
    filters: [
        {
            fieldname: "harness_run",
            label: __("Harness Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Source Harness Run"
        },
        {
            fieldname: "record_type",
            label: __("Record Type"),
            fieldtype: "Select",
            options: "\nSales Invoice\nClaim Line\nRemittance Import\nRemittance Import Line"
        }
    ]
};
