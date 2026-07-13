frappe.ui.form.on("NDIS Next Governed Limited Op Smoke Rollback", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Smoke Rollback Item", {
                rollback: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 13F Smoke"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_payment_entry) {
            frm.add_custom_button(__("Open Rollback Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.rollback_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.rollback_completed) {
            frm.dashboard.set_headline_alert(
                __("Next governed limited-operation smoke rolled back. Freeze rollback evidence next."),
                "green"
            );
        }
    }
});
