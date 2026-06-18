frappe.ui.form.on("NDIS Governed Limited Op Pre Exec", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Pre Exec Item", {
                pre_execution_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Pre Exec Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Pre Exec Guardrail Report");
        }, __("Open"));

        if (frm.doc.readiness) {
            frm.add_custom_button(__("Open Phase 10S Readiness"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Ops Readiness", frm.doc.readiness);
            }, __("Evidence"));
        }

        if (frm.doc.governance_closeout) {
            frm.add_custom_button(__("Open Phase 10R Governance"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Governance Closeout", frm.doc.governance_closeout);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.pre_execution_approved) {
            frm.dashboard.set_headline_alert(
                __("One governed limited operation pre-execution gate approved. No posting performed."),
                "green"
            );
        }
    }
});
