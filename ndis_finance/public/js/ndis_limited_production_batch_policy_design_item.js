frappe.ui.form.on("NDIS Limited Production Batch Policy Design Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.policy_design) {
            frm.add_custom_button(__("Open Policy Design"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Design", frm.doc.policy_design);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
