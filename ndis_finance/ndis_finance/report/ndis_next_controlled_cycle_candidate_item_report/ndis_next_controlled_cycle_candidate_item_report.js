frappe.query_reports["NDIS Next Controlled Cycle Candidate Item Report"] = {
    filters: [
        {
            fieldname: "candidate",
            label: __("Candidate"),
            fieldtype: "Link",
            options: "NDIS Next Controlled Cycle Candidate"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
