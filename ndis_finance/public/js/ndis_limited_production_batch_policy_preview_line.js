frappe.ui.form.on("NDIS Limited Production Batch Policy Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.policy_preview) {
            frm.add_custom_button(__("Open Policy Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Preview", frm.doc.policy_preview);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }

        if (frm.doc.source_preview_line) {
            frm.add_custom_button(__("Open Source Preview Line"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Preview Line", frm.doc.source_preview_line);
            }, __("Source"));
        }
    }
});
