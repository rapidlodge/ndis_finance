frappe.ui.form.on("NDIS Controlled Limited Ops Runtime Watch", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Watch Items"), () => {
            frappe.set_route("List", "NDIS Controlled Limited Ops Runtime Watch Item", {
                watch: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Watch Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Ops Runtime Watch Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Limited Ops Runtime Watch Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 10N Baseline"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Ops Baseline", frm.doc.baseline);
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

        if (frm.doc.watch_active) {
            frm.dashboard.set_headline_alert(
                __("Controlled limited operations runtime watch is active."),
                "green"
            );
        }
    }
});
