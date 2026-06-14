frappe.ui.form.on("NDIS Guarded Limited Operation Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Items"), () => {
            frappe.set_route("List", "NDIS Guarded Limited Operation Preview Item", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Operation Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Operation Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.pre_check) {
            frm.add_custom_button(__("Open Phase 10G Pre Check"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operation Pre Check", frm.doc.pre_check);
            }, __("Evidence"));
        }

        if (frm.doc.monitoring_register) {
            frm.add_custom_button(__("Open Phase 10F Register"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operations Monitoring Register", frm.doc.monitoring_register);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.operation_previewed) {
            frm.dashboard.set_headline_alert(
                __("Preview complete. Ready for single guarded limited operation execution gate."),
                "green"
            );
        }
    }
});