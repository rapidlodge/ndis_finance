frappe.query_reports["NDIS Governed Limited Op Exec Gate Item Report"] = {
    filters: [
        {
            fieldname: "execution_gate",
            label: __("Execution Gate"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Exec Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo"
        }
    ]
};
