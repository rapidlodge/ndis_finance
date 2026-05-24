frappe.query_reports["NDIS Invoice Backed PE Smoke Line Report"] = {
    filters: [
        {
            fieldname: "smoke_run",
            label: __("Smoke Run"),
            fieldtype: "Link",
            options: "NDIS Invoice Backed PE Smoke Run"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        },
        {
            fieldname: "category",
            label: __("Category"),
            fieldtype: "Data"
        }
    ]
};
