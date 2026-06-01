frappe.ui.form.on("NDIS Real Remittance PE Activation Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Activation Gate"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Activation Gate", frm.doc.activation_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
