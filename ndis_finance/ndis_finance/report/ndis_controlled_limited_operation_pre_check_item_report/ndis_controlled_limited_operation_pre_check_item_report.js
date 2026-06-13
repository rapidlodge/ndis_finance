frappe.query_reports["NDIS Controlled Limited Operation Pre Check Item Report"] = {
    filters: [
        {
            fieldname: "pre_check",
            label: __("Pre Check"),
            fieldtype: "Link",
            options: "NDIS Controlled Limited Operation Pre Check"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};