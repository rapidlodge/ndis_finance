frappe.ui.form.on("NDIS Guarded Adapter Smoke Rollback Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Guarded Adapter Smoke Rollback Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Adapter Smoke Rollback Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Guarded Adapter Smoke Rollback Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Phase 10B Rollback"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Adapter Smoke Rollback", frm.doc.rollback);
            }, __("Evidence"));
        }

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 10A Smoke"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Adapter Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.rollback_freeze_allowed) {
            frm.dashboard.set_headline_alert(
                __("Rollback evidence frozen. Ready for final guarded adapter policy review."),
                "green"
            );
        }
    }
});
