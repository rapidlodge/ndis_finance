frappe.ui.form.on("NDIS Controlled Limited Ops Runtime Watch Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.watch) {
            frm.add_custom_button(__("Open Watch"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Ops Runtime Watch", frm.doc.watch);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
