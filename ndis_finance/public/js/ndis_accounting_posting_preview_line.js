frappe.ui.form.on("NDIS Accounting Posting Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.posting_preview) {
            frm.add_custom_button(__("Open Posting Preview"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Preview", frm.doc.posting_preview);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Open"));
        }
    }
});
