frappe.query_reports["NDIS Governed Limited Op Precheck Item Report"] = {
    filters: [
        {
            fieldname: "precheck",
            label: __("Precheck"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Precheck"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
