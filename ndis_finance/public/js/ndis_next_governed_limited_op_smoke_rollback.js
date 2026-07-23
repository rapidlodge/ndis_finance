frappe.ui.form.on("NDIS Next Governed Limited Op Smoke Rollback", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Rollback Items"), () => {
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

        frm.add_custom_button(__("Open Phase 13S Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase13S Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13S Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase13S Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14E Smoke Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase14E Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14E Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase14E Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14Q Smoke Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14Q Smoke Rollback Item Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Item Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 14Q Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Smoke Rollback Phase14Q Guardrail Report");
        }, __("Open"));

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Phase 13F Smoke"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Smoke", frm.doc.smoke);
            }, __("Evidence"));

            frm.add_custom_button(__("Open Phase 13R Smoke"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Smoke", frm.doc.smoke);
            }, __("Evidence"));

            frm.add_custom_button(__("Open Phase 14D Smoke"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Smoke", frm.doc.smoke);
            }, __("Evidence"));

            frm.add_custom_button(__("Open Phase 14P Smoke"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Smoke", frm.doc.smoke);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_payment_entry) {
            frm.add_custom_button(__("Open Rollback Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.rollback_payment_entry);
            }, __("Accounting"));

            frm.add_custom_button(__("Open Rolled Back Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.rollback_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
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

        if (frm.doc.rollback_completed) {
            frm.dashboard.set_headline_alert(
                __("Next governed limited-operation smoke rolled back. Freeze rollback evidence next."),
                "green"
            );
        }
    }
});
