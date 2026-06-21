frappe.ui.form.on("NDIS Governed Limited Op Exec Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Exec Gate Item", {
                execution_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Exec Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Exec Gate Item Report", {
                execution_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Exec Gate Guardrail Report", {
                execution_gate: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.governed_limited_operation_preview) {
            frm.add_custom_button(__("Open Phase 10U Preview"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Preview", frm.doc.governed_limited_operation_preview);
            }, __("Evidence"));
        }

        if (frm.doc.source_payment_entry) {
            frm.add_custom_button(__("Open Source Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.source_payment_entry);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.execution_gate_approved) {
            frm.dashboard.set_headline_alert(
                __("Execution gate approved for the next governed smoke only. Real posting remains disabled."),
                "green"
            );
        }
    }
});
