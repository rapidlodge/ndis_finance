frappe.query_reports["NDIS Real Remittance Batch Source Harness Guardrail Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nSource Created\nNeeds Review\nBlocked\nCancelled"
        }
    ]
};
