frappe.ui.form.on("NDIS PE One Submitted Smoke Run Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.submitted_run) {
            frm.add_custom_button(__("Open Submitted Run"), () => {
                frappe.set_route("Form", "NDIS PE One Submitted Smoke Run", frm.doc.submitted_run);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
