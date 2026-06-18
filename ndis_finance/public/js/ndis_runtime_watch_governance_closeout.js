frappe.ui.form.on("NDIS Runtime Watch Governance Closeout", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Governance Items"), () => {
            frappe.set_route("List", "NDIS Runtime Watch Governance Closeout Item", {
                governance_closeout: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Governance Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Governance Closeout Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Governance Closeout Guardrail Report");
        }, __("Open"));

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 10Q Freeze"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Violation Sim Freeze", frm.doc.freeze);
            }, __("Evidence"));
        }

        if (frm.doc.simulation) {
            frm.add_custom_button(__("Open Phase 10P Simulation"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Violation Sim", frm.doc.simulation);
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

        if (frm.doc.governance_closeout_approved) {
            frm.dashboard.set_headline_alert(
                __("Runtime watch governance closed. Governed controlled limited operations are ready."),
                "green"
            );
        }
    }
});
