frappe.query_reports["NDIS Limited Batch Posting Adapter Preview Item Report"] = {
    filters: [
        {
            fieldname: "adapter_preview",
            label: __("Adapter Preview"),
            fieldtype: "Link",
            options: "NDIS Limited Batch Posting Adapter Preview"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
