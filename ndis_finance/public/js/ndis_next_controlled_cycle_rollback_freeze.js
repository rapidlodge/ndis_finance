frappe.ui.form.on("NDIS Next Controlled Cycle Rollback Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Rollback Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Rollback Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Rollback Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Phase 11W Rollback"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Rollback", frm.doc.rollback);
            }, __("Evidence"));
        }

        if (frm.doc.frozen_payment_entry) {
            frm.add_custom_button(__("Open Frozen Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.frozen_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.freeze_completed) {
            frm.dashboard.set_headline_alert(
                __("Rollback evidence frozen. Next controlled-cycle closeout can proceed."),
                "green"
            );
        }
    }
});
