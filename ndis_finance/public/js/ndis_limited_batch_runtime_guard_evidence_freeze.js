frappe.ui.form.on("NDIS Limited Batch Runtime Guard Evidence Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Evidence Items"), () => {
            frappe.set_route("List", "NDIS Limited Batch Runtime Guard Evidence Item", {
                evidence_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Runtime Guard Evidence Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Batch Runtime Guard Evidence Guardrail Report");
        }, __("Open"));

        if (frm.doc.runtime_guard) {
            frm.add_custom_button(__("Open Phase 9V Guard"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Runtime Guard", frm.doc.runtime_guard);
            }, __("Evidence"));
        }

        if (frm.doc.monitor_gate) {
            frm.add_custom_button(__("Open Phase 9U Monitor"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Use Monitor Gate", frm.doc.monitor_gate);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.runtime_guard_freeze_allowed) {
            frm.dashboard.set_headline_alert(
                __("Runtime guard evidence frozen. Caps are frozen and live posting remains blocked."),
                "green"
            );
        }
    }
});
