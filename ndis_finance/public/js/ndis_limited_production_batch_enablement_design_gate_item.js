frappe.ui.form.on("NDIS Limited Production Batch Enablement Design Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.enablement_gate) {
            frm.add_custom_button(__("Open Enablement Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Design Gate", frm.doc.enablement_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
