frappe.query_reports["NDIS Governed Limited Op Closeout Item Report"] = {
    filters: [
        {
            fieldname: "closeout",
            label: __("Closeout"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Closeout"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        },
        { fieldname: "category", label: __("Category"), fieldtype: "Data" }
    ]
};
