frappe.query_reports["NDIS Controlled Production Batch Adapter Exception Report"] = {
    filters: [
        {
            fieldname: "adapter_run",
            label: __("Adapter Run"),
            fieldtype: "Link",
            options: "NDIS Controlled Production Batch Adapter Run"
        }
    ]
};
