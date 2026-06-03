frappe.query_reports["NDIS Controlled Production Batch Activation Guardrail Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" }
    ]
};
