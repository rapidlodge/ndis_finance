frappe.ui.form.on("NDIS Controlled Production Batch Smoke Evidence Freeze Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.evidence_freeze) {
            frm.add_custom_button(__("Open Evidence Freeze"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Smoke Evidence Freeze", frm.doc.evidence_freeze);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});