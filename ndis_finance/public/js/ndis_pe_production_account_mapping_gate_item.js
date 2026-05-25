frappe.ui.form.on("NDIS PE Production Account Mapping Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.mapping_gate) {
            frm.add_custom_button(__("Open Mapping Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Account Mapping Gate", frm.doc.mapping_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
