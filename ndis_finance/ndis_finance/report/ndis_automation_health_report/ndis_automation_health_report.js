frappe.query_reports["NDIS Automation Health Report"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "run_type",
            label: __("Run Type"),
            fieldtype: "Select",
            options: "\nManual\nScheduled",
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nStarted\nCompleted\nCompleted With Exceptions\nFailed",
        },
    ],
};
