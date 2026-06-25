frappe.ui.form.on("NDIS Governed Next Op Rollback", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Items"), () => {
            frappe.set_route("List", "NDIS Governed Next Op Rollback Item", {
                rollback: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 11J Smoke"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.rolled_back_payment_entry) {
            frm.add_custom_button(__("Open Rolled Back Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.rolled_back_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.rollback_completed) {
            frm.dashboard.set_headline_alert(
                __("Rollback completed. Rollback evidence freeze can proceed."),
                "green"
            );
        }
    }
});