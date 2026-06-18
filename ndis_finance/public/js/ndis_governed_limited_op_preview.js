frappe.ui.form.on("NDIS Governed Limited Op Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Preview Item", {
                preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Preview Guardrail Report");
        }, __("Open"));

        if (frm.doc.pre_execution_gate) {
            frm.add_custom_button(__("Open Phase 10T Gate"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Pre Exec", frm.doc.pre_execution_gate);
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

        if (frm.doc.preview_completed) {
            frm.dashboard.set_headline_alert(
                __("Governed limited operation preview is ready. No posting performed."),
                "green"
            );
        }
    }
});
