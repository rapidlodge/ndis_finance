frappe.query_reports["NDIS Limited Batch Posting Adapter Hard Block Item Report"] = {
    filters: [
        {
            fieldname: "hard_block",
            label: __("Hard Block"),
            fieldtype: "Link",
            options: "NDIS Limited Batch Posting Adapter Hard Block"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nPass\nWarning\nBlocker\nInfo\nCancelled"
        }
    ]
};
