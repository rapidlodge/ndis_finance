frappe.ui.form.on("NDIS Guarded Limited Adapter Smoke Rollback", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Items"), () => {
            frappe.set_route("List", "NDIS Guarded Limited Adapter Smoke Rollback Item", {
                rollback: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Adapter Smoke Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Limited Adapter Smoke Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Cancelled Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 10A Smoke"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Adapter Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_completed && frm.doc.freeze_required_after_rollback) {
            frm.dashboard.set_headline_alert(
                __("Rollback completed. Freeze this rollback evidence in the next phase."),
                "green"
            );
        }
    }
});
