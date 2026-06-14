frappe.ui.form.on("NDIS Guarded Limited Operation Execution Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.gate) {
            frm.add_custom_button(__("Open Gate"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Operation Execution Gate", frm.doc.gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});