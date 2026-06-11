frappe.ui.form.on("NDIS Limited Batch Posting Adapter Preview Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.adapter_preview) {
            frm.add_custom_button(__("Open Adapter Preview"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Posting Adapter Preview", frm.doc.adapter_preview);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
