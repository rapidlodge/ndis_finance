frappe.ui.form.on("NDIS Real Remittance Batch Design Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Design Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Design Gate", frm.doc.design_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
