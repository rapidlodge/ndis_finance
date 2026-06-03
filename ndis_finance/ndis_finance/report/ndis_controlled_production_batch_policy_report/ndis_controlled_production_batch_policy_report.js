frappe.query_reports["NDIS Controlled Production Batch Policy Report"] = {
    filters: [
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nActive\nInactive\nArchived" },
        { fieldname: "policy_type", label: __("Policy Type"), fieldtype: "Select", options: "\nEligibility\nBatch Cap\nAccount Mapping\nSafety Guardrail\nRollback Requirement\nFreeze Requirement" }
    ]
};
