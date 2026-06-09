frappe.ui.form.on("NDIS Limited Production Batch Policy Enablement Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.enablement_run) {
            frm.add_custom_button(__("Open Enablement Run"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Enablement Run", frm.doc.enablement_run);
            }, __("Open"));
        }

        if (frm.doc.policy_doctype && frm.doc.policy_name) {
            frm.add_custom_button(__("Open Policy"), () => {
                frappe.set_route("Form", frm.doc.policy_doctype, frm.doc.policy_name);
            }, __("Policy"));
        }
    }
});
