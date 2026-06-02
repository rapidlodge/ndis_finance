frappe.ui.form.on("NDIS Real Remittance Batch Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.batch_preview) {
            frm.add_custom_button(__("Open Batch Preview"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Preview", frm.doc.batch_preview);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }
    }
});
