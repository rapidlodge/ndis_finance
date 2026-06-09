frappe.ui.form.on("NDIS Limited Production Batch Enablement Readiness Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Readiness Gate Item", {
                readiness_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Readiness Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Readiness Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Readiness Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.evidence_freeze) {
            frm.add_custom_button(__("Open Phase 9Q Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Evidence Freeze", frm.doc.evidence_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 9P Rollback"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_controlled_policy_enablement) {
            frm.dashboard.set_headline_alert(
                __("Readiness approved. Ready for controlled limited production policy enablement. No policy or accounting movement occurred."),
                "green"
            );
        }
    }
});
