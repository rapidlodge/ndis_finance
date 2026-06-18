frappe.ui.form.on("NDIS Governed Limited Ops Readiness", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Readiness Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Ops Readiness Item", {
                readiness: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Readiness Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Ops Readiness Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Ops Readiness Guardrail Report");
        }, __("Open"));

        if (frm.doc.governance_closeout) {
            frm.add_custom_button(__("Open Phase 10R Governance Closeout"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Governance Closeout", frm.doc.governance_closeout);
            }, __("Evidence"));
        }

        if (frm.doc.runtime_watch) {
            frm.add_custom_button(__("Open Phase 10O Runtime Watch"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Ops Runtime Watch", frm.doc.runtime_watch);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.readiness_approved) {
            frm.dashboard.set_headline_alert(
                __("Governed controlled limited operations readiness approved."),
                "green"
            );
        }
    }
});
