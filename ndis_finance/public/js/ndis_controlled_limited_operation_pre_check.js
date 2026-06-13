frappe.ui.form.on("NDIS Controlled Limited Operation Pre Check", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Pre Check Items"), () => {
            frappe.set_route("List", "NDIS Controlled Limited Operation Pre Check Item", {
                pre_check: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Pre Check Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Operation Pre Check Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Operation Pre Check Guardrail Report");
        }, __("Open"));

        if (frm.doc.monitoring_register) {
            frm.add_custom_button(__("Open Phase 10F Register"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operations Monitoring Register", frm.doc.monitoring_register);
            }, __("Evidence"));
        }

        if (frm.doc.decision) {
            frm.add_custom_button(__("Open Phase 10E Decision"), () => {
                frappe.set_route("Form", "NDIS Guarded Adapter Final Policy Decision", frm.doc.decision);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.pre_operation_check_approved) {
            frm.dashboard.set_headline_alert(
                __("Pre-operation check approved for one guarded limited operation preview only."),
                "green"
            );
        }
    }
});