frappe.query_reports["NDIS Governed Limited Op Candidate Item Report"] = {
    filters: [
        {
            fieldname: "candidate",
            label: __("Candidate"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Candidate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
