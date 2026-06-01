frappe.ui.form.on("NDIS Real Remittance PE Rollback Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Rollback Run"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Rollback Run", frm.doc.rollback_run);
            }, __("Open"));
        }

        if (frm.doc.record_doctype && frm.doc.record_name) {
            frm.add_custom_button(__("Open Record"), () => {
                frappe.set_route("Form", frm.doc.record_doctype, frm.doc.record_name);
            }, __("Evidence"));
        }
    }
});
