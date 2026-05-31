frappe.query_reports["NDIS PE Smoke Rollback GL Report"] = {
    filters: [
        {
            fieldname: "voucher_type",
            label: __("Voucher Type"),
            fieldtype: "Select",
            options: "\nPayment Entry\nSales Invoice"
        },
        {
            fieldname: "voucher_no",
            label: __("Voucher No"),
            fieldtype: "Data"
        }
    ]
};
