frappe.query_reports["NDIS Next Governed Limited Op Candidate Validation Phase14A Item Report"] = {
    filters: [
        {
            fieldname: "candidate_validation",
            label: __("Candidate Validation"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Candidate Validation"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
