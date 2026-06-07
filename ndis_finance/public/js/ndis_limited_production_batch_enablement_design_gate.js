frappe.ui.form.on("NDIS Limited Production Batch Enablement Design Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Enablement Design Gate Item", {
                enablement_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Enablement Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Design Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Enablement Design Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.policy_lock) {
            frm.add_custom_button(__("Open Phase 9J Policy Lock"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Lock", frm.doc.policy_lock);
            }, __("Evidence"));
        }

        if (frm.doc.finalisation_gate) {
            frm.add_custom_button(__("Open Phase 9I Finalisation Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Finalisation Gate", frm.doc.finalisation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Cancelled Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.ready_for_limited_enablement_preview) {
            frm.dashboard.set_headline_alert(
                __("Enablement design approved. Ready for controlled limited enablement preview. Live posting remains disabled."),
                "green"
            );
        }
    }
});
