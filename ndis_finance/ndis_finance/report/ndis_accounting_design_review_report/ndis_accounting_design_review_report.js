frappe.query_reports["NDIS Accounting Design Review Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Reviewed From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Reviewed To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPassed\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "design_approved_for_next_phase",
            label: __("Approved For Next Phase"),
            fieldtype: "Select",
            options: "\n1\n0"
        }
    ]
};
