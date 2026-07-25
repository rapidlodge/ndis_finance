frappe.ui.form.on("NDIS Next Governed Limited Op Closeout", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Closeout Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Closeout Item", {
                closeout: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Closeout Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Guardrail Report");
        }, __("Open"));

        if (frm.doc.closeout_payment_entry === "ACC-PAY-2026-00015") {
            frm.add_custom_button(__("Open Phase 13U Closeout Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Phase13U Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 13U Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Phase13U Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.closeout_payment_entry === "ACC-PAY-2026-00016") {
            frm.add_custom_button(__("Open Phase 14G Closeout Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Phase14G Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 14G Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Phase14G Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.closeout_payment_entry === "ACC-PAY-2026-00017") {
            frm.add_custom_button(__("Open Phase 14S Closeout Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Phase14S Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 14S Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Closeout Phase14S Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 13T Rollback Freeze"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Rollback Freeze", frm.doc.freeze);
            }, __("Evidence"));

            if (frm.doc.closeout_payment_entry === "ACC-PAY-2026-00016") {
                frm.add_custom_button(__("Open Phase 14F Rollback Freeze"), () => {
                    frappe.set_route("Form", "NDIS Next Governed Limited Op Rollback Freeze", frm.doc.freeze);
                }, __("Evidence"));
            }

            if (frm.doc.closeout_payment_entry === "ACC-PAY-2026-00017") {
                frm.add_custom_button(__("Open Phase 14R Rollback Freeze"), () => {
                    frappe.set_route("Form", "NDIS Next Governed Limited Op Rollback Freeze", frm.doc.freeze);
                }, __("Evidence"));
            }
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.closeout_payment_entry) {
            frm.add_custom_button(__("Open Closed Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.closeout_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.previous_gated_payment_entry) {
            frm.add_custom_button(__("Open Previous Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.historical_gated_payment_entry) {
            frm.add_custom_button(__("Open Historical Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.historical_gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.closeout_completed) {
            frm.dashboard.set_headline_alert(
                __("Next governed limited-operation cycle closed. Steady-state baseline can proceed next."),
                "green"
            );
        }
    }
});
