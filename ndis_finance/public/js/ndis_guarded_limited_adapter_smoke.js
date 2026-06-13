frappe.ui.form.on("NDIS Guarded Limited Adapter Smoke", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Items"), () => {
            frappe.set_route("List", "NDIS Guarded Limited Adapter Smoke Item", {
                smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Adapter Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Adapter Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Phase 9Z Gate"), () => {
                frappe.set_route("Form", "NDIS Limited Batch Adapter Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.adapter_smoke_completed && frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Smoke completed. Rollback is required before freeze."),
                "orange"
            );
        }
    }
});
