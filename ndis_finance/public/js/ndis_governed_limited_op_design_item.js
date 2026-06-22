frappe.ui.form.on("NDIS Governed Limited Op Design Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.design) {
            frm.add_custom_button(__("Open Design"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Design", frm.doc.design);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
