frappe.ui.form.on("NDIS Sandbox Accounting Cleanup Pack Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.cleanup_pack) {
            frm.add_custom_button(__("Open Cleanup Pack"), () => {
                frappe.set_route("Form", "NDIS Sandbox Accounting Cleanup Pack", frm.doc.cleanup_pack);
            }, __("Open"));
        }

        if (frm.doc.record_doctype && frm.doc.record_name && frm.doc.record_exists_after) {
            frm.add_custom_button(__("Open Record"), () => {
                frappe.set_route("Form", frm.doc.record_doctype, frm.doc.record_name);
            }, __("Open"));
        }
    }
});
