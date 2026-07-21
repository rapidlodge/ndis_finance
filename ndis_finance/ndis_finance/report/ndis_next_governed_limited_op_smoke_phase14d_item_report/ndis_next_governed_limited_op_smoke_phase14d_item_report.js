frappe.query_reports["NDIS Next Governed Limited Op Smoke Phase14D Item Report"] = {
    filters: [
        {
            fieldname: "smoke",
            label: __("Smoke"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Smoke"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
