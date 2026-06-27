frappe.ui.form.on("NDIS Next Controlled Cycle Exec Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Exec Gate Item", {
                execution_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Exec Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Exec Gate Guardrail Report");
        }, __("Open"));

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 11T Preview"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.execution_gate_approved) {
            frm.dashboard.set_headline_alert(
                __("Execution gate approved for smoke-only controlled cycle. Real production posting remains blocked."),
                "green"
            );
        }
    }
});
