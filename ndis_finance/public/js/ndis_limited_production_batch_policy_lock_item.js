frappe.ui.form.on("NDIS Limited Production Batch Policy Lock Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.policy_lock) {
            frm.add_custom_button(__("Open Policy Lock"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Lock", frm.doc.policy_lock);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
