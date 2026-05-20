frappe.ui.form.on("NDIS Accounting Design Review Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.design_review) {
            frm.add_custom_button(__("Open Design Review"), () => {
                frappe.set_route("Form", "NDIS Accounting Design Review", frm.doc.design_review);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
