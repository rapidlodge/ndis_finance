frappe.query_reports["NDIS PE One Submitted Smoke GL Report"] = {
    filters: [
        {
            fieldname: "payment_entry",
            label: __("Payment Entry"),
            fieldtype: "Link",
            options: "Payment Entry"
        }
    ]
};
