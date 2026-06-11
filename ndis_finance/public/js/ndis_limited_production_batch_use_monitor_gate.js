frappe.ui.form.on("NDIS Limited Production Batch Use Monitor Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Monitor Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Use Monitor Item", {
                monitor_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Monitor Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Use Monitor Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Use Monitor Guardrail Report");
        }, __("Open"));

        if (frm.doc.policy_enablement_freeze) {
            frm.add_custom_button(__("Open Phase 9T Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Enablement Freeze", frm.doc.policy_enablement_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.enablement_run) {
            frm.add_custom_button(__("Open Phase 9S Enablement"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Enablement Run", frm.doc.enablement_run);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.ready_for_operational_monitoring) {
            frm.dashboard.set_headline_alert(
                __("Operational monitoring approved. Controlled policy remains enabled and live posting remains blocked."),
                "green"
            );
        }
    }
});
