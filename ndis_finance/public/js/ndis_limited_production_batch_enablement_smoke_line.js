frappe.ui.form.on("NDIS Limited Production Batch Enablement Smoke Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.enablement_smoke) {
            frm.add_custom_button(__("Open Smoke Run"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Smoke Run", frm.doc.enablement_smoke);
            }, __("Open"));
        }

        if (frm.doc.policy_doctype && frm.doc.policy_name) {
            frm.add_custom_button(__("Open Policy"), () => {
                frappe.set_route("Form", frm.doc.policy_doctype, frm.doc.policy_name);
            }, __("Policy"));
        }
    }
});
