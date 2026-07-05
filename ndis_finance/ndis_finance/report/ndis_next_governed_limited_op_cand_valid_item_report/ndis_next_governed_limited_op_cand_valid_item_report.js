frappe.query_reports["NDIS Next Governed Limited Op Cand Valid Item Report"] = {
    filters: [
        {
            fieldname: "candidate_validation",
            label: __("Candidate Validation"),
            fieldtype: "Link",
            options: "NDIS Next Governed Limited Op Cand Valid"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};