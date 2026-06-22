frappe.query_reports["NDIS Governed Limited Op Candidate Validation Item Report"] = {
    filters: [
        {
            fieldname: "validation",
            label: __("Validation"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Candidate Validation"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
