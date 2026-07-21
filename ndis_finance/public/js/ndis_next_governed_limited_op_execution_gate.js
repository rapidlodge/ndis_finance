frappe.ui.form.on("NDIS Next Governed Limited Op Execution Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Execution Gate Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Execution Gate Item", {
                execution_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Execution Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Execution Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Execution Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.gated_payment_entry === "ACC-PAY-2026-00015") {
            frm.add_custom_button(__("Open Phase 14C Execution Gate Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Execution Gate Phase14C Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 14C Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Execution Gate Phase14C Guardrail Report");
            }, __("Open"));
        } else {
            frm.add_custom_button(__("Open Phase 13Q Execution Gate Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Execution Gate Phase13Q Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 13Q Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Execution Gate Phase13Q Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.preview) {
            const preview_label = frm.doc.gated_payment_entry === "ACC-PAY-2026-00015"
                ? __("Open Phase 14B Preview")
                : __("Open Phase 13P Preview");
            frm.add_custom_button(preview_label, () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        } else if (frm.doc.execution_gate_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.execution_gate_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.previous_gated_payment_entry) {
            frm.add_custom_button(__("Open Previous Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.execution_gate_approved) {
            frm.dashboard.set_headline_alert(
                __("Next governed limited-operation execution gate approved. Smoke can proceed next."),
                "green"
            );
        }
    }
});
