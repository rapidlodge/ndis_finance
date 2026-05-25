frappe.query_reports["NDIS PE Production Design Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nDesign Approved\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "design_status",
            label: __("Design Status"),
            fieldtype: "Select",
            options: "\nReady For Controlled Activation Design\nReady With Warnings\nNeeds Review\nBlocked"
        }
    ]
};
