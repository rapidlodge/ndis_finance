frappe.ui.form.on("NDIS Runtime Watch Violation Sim", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.simulation_completed) {
            frm.dashboard.add_indicator(__("Simulation Completed"), "green");
        }

        frm.add_custom_button(__("Open Simulation Items"), () => {
            frappe.set_route("List", "NDIS Runtime Watch Violation Sim Item", {
                simulation: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Simulation Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Violation Sim Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Violation Sim Item Report", {
                simulation: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Runtime Watch Violation Sim Guardrail Report");
        }, __("Open"));

        if (frm.doc.runtime_watch) {
            frm.add_custom_button(__("Open Phase 10O Runtime Watch"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Ops Runtime Watch", frm.doc.runtime_watch);
            }, __("Evidence"));
        }

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 10N Baseline"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Ops Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.target_policy) {
            frm.add_custom_button(__("Open Target Policy"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Posting Policy", frm.doc.target_policy);
            }, __("Evidence"));
        }
    }
});
