frappe.ui.form.on("NDIS Next Governed Limited Op Rollback Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Rollback Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Rollback Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Rollback Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.freeze_payment_entry === "ACC-PAY-2026-00015") {
            frm.add_custom_button(__("Open Phase 13T Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Rollback Freeze Phase13T Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 13T Guardrails"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Rollback Freeze Phase13T Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Smoke Rollback"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Smoke Rollback", frm.doc.rollback);
            }, __("Evidence"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.freeze_payment_entry) {
            frm.add_custom_button(__("Open Frozen Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.freeze_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.freeze_completed) {
            frm.dashboard.set_headline_alert(
                __("Rollback evidence frozen. Closeout gate can proceed next."),
                "green"
            );
        }
    }
});
