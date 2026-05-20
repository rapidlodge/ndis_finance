frappe.ui.form.on("NDIS Accounting Posting Request Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.posting_request) {
            frm.add_custom_button(__("Open Posting Request"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Request", frm.doc.posting_request);
            }, __("Open"));
        }

        if (frm.doc.posting_preview_line) {
            frm.add_custom_button(__("Open Preview Line"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Preview Line", frm.doc.posting_preview_line);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Open"));
        }
    }
});
