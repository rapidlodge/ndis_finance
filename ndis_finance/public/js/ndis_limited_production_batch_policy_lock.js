frappe.ui.form.on("NDIS Limited Production Batch Policy Lock", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Lock Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Policy Lock Item", {
                policy_lock: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Lock Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Lock Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Policy Lock Guardrail Report");
        }, __("Open"));

        if (frm.doc.finalisation_gate) {
            frm.add_custom_button(__("Open Phase 9I Finalisation Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Finalisation Gate", frm.doc.finalisation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.phase9h_freeze) {
            frm.add_custom_button(__("Open Phase 9H Freeze"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Smoke Evidence Freeze", frm.doc.phase9h_freeze);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Cancelled Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.ready_for_limited_enablement_design) {
            frm.dashboard.set_headline_alert(
                __("Policy locked for controlled limited production use. Ready for limited enablement design. Live posting remains disabled."),
                "green"
            );
        }
    }
});
