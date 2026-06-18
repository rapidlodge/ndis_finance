frappe.query_reports["NDIS Governed Limited Ops Readiness Item Report"] = {
    filters: [
        {
            fieldname: "readiness",
            label: __("Readiness"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Ops Readiness"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
