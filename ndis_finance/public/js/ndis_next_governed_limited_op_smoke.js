frappe.ui.form.on("NDIS Next Governed Limited Op Smoke", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Smoke Item", {
                smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13R Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Phase13R Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13R Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Phase13R Guardrail Report");
        }, __("Open"));

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Phase 13Q Execution Gate"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Execution Gate", frm.doc.execution_gate);
            }, __("Evidence"));
        }

        if (frm.doc.smoke_payment_entry) {
            frm.add_custom_button(__("Open Smoke Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.smoke_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.previous_monitored_payment_entry) {
            frm.add_custom_button(__("Open Previous Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke_completed) {
            frm.dashboard.set_headline_alert(
                __("Next governed limited-operation smoke submitted. Smoke rollback is required next."),
                "orange"
            );
        }
    }
});
