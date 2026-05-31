frappe.query_reports["NDIS Real Remittance PE Preview Line Report"] = {
    filters: [
        {
            fieldname: "preview",
            label: __("Preview"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Preview"
        },
        {
            fieldname: "preview_status",
            label: __("Preview Status"),
            fieldtype: "Select",
            options: "\nEligible\nBlocked\nReview\nCancelled"
        },
        {
            fieldname: "classification",
            label: __("Classification"),
            fieldtype: "Select",
            options: "\nEligible Paid\nEligible Short Paid\nBlocked Rejected\nBlocked Duplicate\nBlocked Unmatched\nBlocked Overpayment\nBlocked Cross-company\nBlocked Missing Invoice / Claim Line\nBlocked Batch Cap\nReview Required"
        }
    ]
};
