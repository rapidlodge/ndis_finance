frappe.ui.form.on("NDIS Executive Governance Pack Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.governance_pack) {
            frm.add_custom_button(__("Open Governance Pack"), () => {
                frappe.set_route("Form", "NDIS Executive Governance Pack", frm.doc.governance_pack);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
