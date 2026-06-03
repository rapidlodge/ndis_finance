frappe.ui.form.on("NDIS Controlled Production Batch Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Preview"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Preview", frm.doc.preview);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }
    }
});
