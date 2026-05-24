frappe.query_reports["NDIS PE Sandbox Readiness Freeze Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Frozen From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Frozen To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nFrozen\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "readiness_status",
            label: __("Readiness Status"),
            fieldtype: "Select",
            options: "\nReady For Next Design Phase\nReady With Warnings\nNeeds Review\nBlocked"
        }
    ]
};
