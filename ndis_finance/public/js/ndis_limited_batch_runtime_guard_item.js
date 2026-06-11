frappe.ui.form.on("NDIS Limited Batch Runtime Guard Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.runtime_guard) {
            frm.add_custom_button(__("Open Runtime Guard"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Runtime Guard", frm.doc.runtime_guard);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
