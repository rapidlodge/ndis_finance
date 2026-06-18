frappe.query_reports["NDIS Governed Limited Op Pre Exec Item Report"] = {
    filters: [
        {
            fieldname: "pre_execution_gate",
            label: __("Pre-Execution Gate"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Pre Exec"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
