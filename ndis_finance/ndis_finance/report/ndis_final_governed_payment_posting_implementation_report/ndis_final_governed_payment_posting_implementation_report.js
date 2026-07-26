frappe.query_reports["NDIS Final Governed Payment Posting Implementation Report"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nNeeds Review\nRuntime Monitor Active\nCancelled"
        }
    ]
};
