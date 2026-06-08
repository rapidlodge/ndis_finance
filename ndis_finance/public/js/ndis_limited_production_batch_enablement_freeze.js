frappe.ui.form.on("NDIS Limited Production Batch Enablement Evidence Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Lines"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Evidence Freeze Line", {
                evidence_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 9P Rollback"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.enablement_smoke) {
            frm.add_custom_button(__("Open Phase 9O Smoke"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Enablement Smoke Run", frm.doc.enablement_smoke);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.ready_for_next_phase) {
            frm.dashboard.set_headline_alert(
                __("Limited enablement smoke and rollback evidence frozen. Ready for next phase."),
                "green"
            );
        }
    }
});
