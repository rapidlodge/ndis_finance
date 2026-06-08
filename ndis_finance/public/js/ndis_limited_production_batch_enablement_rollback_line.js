frappe.ui.form.on("NDIS Limited Production Batch Enablement Rollback Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Rollback Run"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Rollback Run", frm.doc.rollback_run);
            }, __("Open"));
        }

        if (frm.doc.policy_doctype && frm.doc.policy_name) {
            frm.add_custom_button(__("Open Policy"), () => {
                frappe.set_route("Form", frm.doc.policy_doctype, frm.doc.policy_name);
            }, __("Policy"));
        }
    }
});
