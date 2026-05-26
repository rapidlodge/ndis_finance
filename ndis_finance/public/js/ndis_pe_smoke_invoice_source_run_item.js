frappe.ui.form.on("NDIS PE Smoke Invoice Source Run Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.source_run) {
            frm.add_custom_button(__("Open Source Run"), () => {
                frappe.set_route("Form", "NDIS PE Smoke Invoice Source Run", frm.doc.source_run);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
