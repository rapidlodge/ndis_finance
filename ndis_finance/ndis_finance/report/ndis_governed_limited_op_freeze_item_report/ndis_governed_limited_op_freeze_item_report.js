frappe.query_reports["NDIS Governed Limited Op Freeze Item Report"] = {
    filters: [
        {
            fieldname: "freeze",
            label: __("Freeze"),
            fieldtype: "Link",
            options: "NDIS Governed Limited Op Freeze"
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
