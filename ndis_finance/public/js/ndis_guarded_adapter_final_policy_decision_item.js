frappe.ui.form.on("NDIS Guarded Adapter Final Policy Decision Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.decision) {
            frm.add_custom_button(__("Open Decision"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Final Policy Decision", frm.doc.decision);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
