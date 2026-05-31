frappe.ui.form.on("NDIS PE Smoke Rollback Run Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Rollback Run"), () => {
                frappe.set_route("Form", "NDIS PE Smoke Rollback Run", frm.doc.rollback_run);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
