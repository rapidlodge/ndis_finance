frappe.query_reports["NDIS Controlled Production Batch Design Gate Report"] = {
    filters: [
        { fieldname: "from_date", label: __("Checked From"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("Checked To"), fieldtype: "Date" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nNeeds Review\nApproved\nBlocked\nCancelled" }
    ]
};
