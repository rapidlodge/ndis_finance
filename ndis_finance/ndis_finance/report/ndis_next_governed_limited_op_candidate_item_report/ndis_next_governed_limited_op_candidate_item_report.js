frappe.query_reports["NDIS Next Governed Limited Op Candidate Item Report"] = {
    filters: [
        {
            fieldname: "candidate_selection",
            label: __("Candidate Selection"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Candidate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
