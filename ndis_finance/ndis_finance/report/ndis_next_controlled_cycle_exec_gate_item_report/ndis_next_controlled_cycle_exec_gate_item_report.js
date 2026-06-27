frappe.query_reports["NDIS Next Controlled Cycle Exec Gate Item Report"] = {
    filters: [
        {
            fieldname: "execution_gate",
            label: __("Execution Gate"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Exec Gate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
