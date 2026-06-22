frappe.ui.form.on("NDIS Governed Limited Op Precheck Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.precheck) {
            frm.add_custom_button(__("Open Precheck"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Precheck", frm.doc.precheck);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Evidence"));
        }
    }
});
