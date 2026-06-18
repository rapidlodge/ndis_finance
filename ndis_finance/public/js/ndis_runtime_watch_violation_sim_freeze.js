frappe.ui.form.on("NDIS Runtime Watch Violation Sim Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.freeze_completed) {
            frm.dashboard.add_indicator(__("Frozen"), "green");
        }

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Runtime Watch Violation Sim Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Violation Sim Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Violation Sim Freeze Guardrail Report");
        }, __("Open"));

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
    }
});
