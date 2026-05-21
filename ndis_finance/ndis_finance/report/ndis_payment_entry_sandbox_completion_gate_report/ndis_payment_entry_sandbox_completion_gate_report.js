frappe.query_reports["NDIS Payment Entry Sandbox Completion Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nDraft\nPassed\nNeeds Review\nBlocked\nCancelled"
        },
        {
            fieldname: "completion_status",
            label: __("Completion Status"),
            fieldtype: "Select",
            options: "\nStructurally Ready\nReady With Pending Smoke Test\nNeeds Review\nBlocked"
        },
        {
            fieldname: "invoice_backed_smoke_test_pending",
            label: __("Invoice-backed Smoke Pending"),
            fieldtype: "Select",
            options: "\n1\n0"
        }
    ]
};
