frappe.query_reports["NDIS Payment Entry Allocation Exception Report"] = {
    filters: [
        {
            fieldname: "allocation_preview",
            label: __("Allocation Preview"),
            fieldtype: "Link",
            options: "NDIS Payment Entry Allocation Preview"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nAllocatable\nException\nDuplicate\nExcluded\nCancelled"
        },
        {
            fieldname: "allocation_decision",
            label: __("Allocation Decision"),
            fieldtype: "Data"
        },
        {
            fieldname: "sales_invoice",
            label: __("Sales Invoice"),
            fieldtype: "Link",
            options: "Sales Invoice"
        }
    ]
};
