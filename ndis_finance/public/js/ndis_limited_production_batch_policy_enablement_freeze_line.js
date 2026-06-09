frappe.ui.form.on("NDIS Limited Production Batch Policy Enablement Freeze Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.evidence_freeze) {
            frm.add_custom_button(__("Open Evidence Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Enablement Freeze", frm.doc.evidence_freeze);
            }, __("Open"));
        }

        if (frm.doc.policy_doctype && frm.doc.policy_name) {
            frm.add_custom_button(__("Open Policy"), () => {
                frappe.set_route("Form", frm.doc.policy_doctype, frm.doc.policy_name);
            }, __("Policy"));
        }
    }
});
