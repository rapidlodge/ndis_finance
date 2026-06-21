frappe.query_reports["NDIS Governed Limited Op Closeout Guardrail Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "\nCloseout Approved\nNeeds Review\nCancelled\nBlocked"
        }
    ]
};
