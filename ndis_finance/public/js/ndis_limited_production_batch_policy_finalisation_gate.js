frappe.ui.form.on("NDIS Limited Production Batch Policy Finalisation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Policy Finalisation Gate Item", {
                finalisation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Finalisation Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Finalisation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Finalisation Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.phase9h_freeze) {
            frm.add_custom_button(__("Open Phase 9H Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Smoke Evidence Freeze", frm.doc.phase9h_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 9G Rollback"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Smoke Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Cancelled Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.ready_for_limited_policy_lock) {
            frm.dashboard.set_headline_alert(
                __("Finalisation approved. Ready for limited production batch policy lock. Live posting remains disabled."),
                "green"
            );
        }
    }
});