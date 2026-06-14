frappe.ui.form.on("NDIS Single Guarded Limited Operation Smoke Rollback Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Rollback"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Limited Operation Smoke Rollback", frm.doc.rollback);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});