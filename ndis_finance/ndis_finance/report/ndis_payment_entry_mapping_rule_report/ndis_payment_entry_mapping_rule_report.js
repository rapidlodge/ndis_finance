frappe.query_reports["NDIS Payment Entry Mapping Rule Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nActive\nSuspended\nRetired"
        },
        {
            fieldname: "payer_type",
            label: __("Payer Type"),
            fieldtype: "Select",
            options: "\nNDIA\nPlan Manager\nParticipant / Nominee\nOther"
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company"
        }
    ]
};
