frappe.query_reports["NDIS Next Governed Limited Op Execution Gate Item Report"] = {
    filters: [
        {
            fieldname: "execution_gate",
            label: __("Execution Gate"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Execution Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
