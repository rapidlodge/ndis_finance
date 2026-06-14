frappe.ui.form.on("NDIS Single Guarded Limited Operation Smoke Rollback", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Items"), () => {
            frappe.set_route("List", "NDIS Single Guarded Limited Operation Smoke Rollback Item", {
                rollback: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Single Guarded Limited Operation Smoke Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Single Guarded Limited Operation Smoke Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 10J Smoke"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Limited Operation Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_completed) {
            frm.dashboard.set_headline_alert(
                __("Rollback completed. Ready for Phase 10L evidence freeze."),
                "green"
            );
        }
    }
});