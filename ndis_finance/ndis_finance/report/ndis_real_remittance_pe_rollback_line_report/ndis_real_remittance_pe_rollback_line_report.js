frappe.query_reports["NDIS Real Remittance PE Rollback Line Report"] = {
    filters: [
        {
            fieldname: "rollback_run",
            label: __("Rollback Run"),
            fieldtype: "Link",
            options: "NDIS Real Remittance PE Rollback Run"
        },
        { fieldname: "record_type", label: __("Record Type"), fieldtype: "Data" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nValidated\nCancelled\nRestored\nBlocked\nInfo"
        }
    ]
};
