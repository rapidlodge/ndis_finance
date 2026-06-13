frappe.ui.form.on("NDIS Guarded Adapter Final Policy Review Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.review) {
            frm.add_custom_button(__("Open Review"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Final Policy Review", frm.doc.review);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
