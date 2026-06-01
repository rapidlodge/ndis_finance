frappe.query_reports["NDIS Real Remittance PE Smoke Line Report"] = {
    filters: [
        {
            fieldname: "smoke_run",
            label: __("Smoke Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Smoke Run"
        },
        {
            fieldname: "record_type",
            label: __("Record Type"),
            fieldtype: "Select",
            options: "\nSource Invoice\nPayment Entry\nSales Invoice"
        }
    ]
};
