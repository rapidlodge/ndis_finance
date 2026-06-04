frappe.ui.form.on("NDIS Controlled Production Batch Policy Review Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.policy_review_gate) {
            frm.add_custom_button(__("Open Policy Review Gate"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Policy Review Gate", frm.doc.policy_review_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
