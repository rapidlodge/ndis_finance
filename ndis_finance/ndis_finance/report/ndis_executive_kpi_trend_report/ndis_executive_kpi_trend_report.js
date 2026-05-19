frappe.query_reports["NDIS Executive KPI Trend Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Snapshot From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Snapshot To Date"), fieldtype: "Date" },
        {
            fieldname: "snapshot_type",
            label: __("Snapshot Type"),
            fieldtype: "Select",
            options: "\nManual\nScheduled"
        },
        { fieldname: "house", label: __("House"), fieldtype: "Link", options: "NDIS House" },
        { fieldname: "participant", label: __("Participant"), fieldtype: "Link", options: "Customer" }
    ]
};
