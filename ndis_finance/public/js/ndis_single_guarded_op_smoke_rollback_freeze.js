frappe.ui.form.on("NDIS Single Guarded Op Smoke Rollback Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Single Guarded Op Smoke Rollback Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Single Guarded Op Smoke Rollback Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Single Guarded Op Smoke Rollback Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Phase 10K Rollback"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Limited Operation Smoke Rollback", frm.doc.rollback);
            }, __("Evidence"));
        }

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 10J Smoke"), () => {
                frappe.set_route("Form", "NDIS Single Guarded Limited Operation Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.freeze_completed) {
            frm.dashboard.set_headline_alert(
                __("Evidence frozen. Ready for final limited operation closeout."),
                "green"
            );
        }
    }
});
