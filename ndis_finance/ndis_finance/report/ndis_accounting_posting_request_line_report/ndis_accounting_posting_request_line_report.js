frappe.query_reports["NDIS Accounting Posting Request Line Report"] = {
    filters: [
        { fieldname: "posting_request", label: __("Posting Request"), fieldtype: "Link", options: "NDIS Accounting Posting Request" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nReady\nWarning\nBlocker\nSimulated\nCancelled"
        },
        {
            fieldname: "line_type",
            label: __("Line Type"),
            fieldtype: "Select",
            options: "\nDebit\nCredit\nControl\nInformation"
        },
        { fieldname: "target_entry_type", label: __("Target Entry Type"), fieldtype: "Data" }
    ]
};
