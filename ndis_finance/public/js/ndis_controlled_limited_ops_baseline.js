frappe.ui.form.on("NDIS Controlled Limited Ops Baseline", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Baseline Items"), () => {
            frappe.set_route("List", "NDIS Controlled Limited Ops Baseline Item", {
                baseline: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Baseline Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Ops Baseline Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Ops Baseline Guardrail Report");
        }, __("Open"));

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Phase 10M Closeout"), () => {
                frappe.set_route("Form", "NDIS Limited Operation Closeout Gate", frm.doc.closeout);
            }, __("Evidence"));
        }

        if (frm.doc.monitoring_register) {
            frm.add_custom_button(__("Open Monitoring Register"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operations Monitoring Register", frm.doc.monitoring_register);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy_doctype && frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", frm.doc.target_policy_doctype, frm.doc.target_policy);
            }, __("Policy"));
        }

        if (frm.doc.baseline_active) {
            frm.dashboard.set_headline_alert(
                __("Controlled limited operations steady-state baseline is active."),
                "green"
            );
        }
    }
});
