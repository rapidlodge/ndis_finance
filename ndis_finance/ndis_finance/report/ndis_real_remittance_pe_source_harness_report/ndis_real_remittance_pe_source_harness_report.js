frappe.query_reports["NDIS Real Remittance PE Source Harness Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPreviewed\nNeeds Review\nSource Created\nSource Ready\nCancelled"
        }
    ]
};
