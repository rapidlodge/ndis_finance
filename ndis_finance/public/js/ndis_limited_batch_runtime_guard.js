frappe.ui.form.on("NDIS Limited Batch Runtime Guard", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Guard Items"), () => {
            frappe.set_route("List", "NDIS Limited Batch Runtime Guard Item", {
                runtime_guard: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guard Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Runtime Guard Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Runtime Guard Guardrail Report");
        }, __("Open"));

        if (frm.doc.monitor_gate) {
            frm.add_custom_button(__("Open Phase 9U Monitor"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Use Monitor Gate", frm.doc.monitor_gate);
            }, __("Evidence"));
        }

        if (frm.doc.policy_enablement_freeze) {
            frm.add_custom_button(__("Open Phase 9T Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Enablement Freeze", frm.doc.policy_enablement_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.runtime_guard_active) {
            frm.dashboard.set_headline_alert(
                __("Runtime guard active. Caps enforced and live posting remains blocked."),
                "green"
            );
        }
    }
});
