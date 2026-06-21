frappe.ui.form.on("NDIS Governed Limited Op Closeout Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Closeout"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Closeout", frm.doc.closeout);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Evidence"));
        }
    }
});
