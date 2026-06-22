frappe.ui.form.on("NDIS Governed Next Op Preview Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Preview"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Preview", frm.doc.preview);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
