frappe.ui.form.on("NDIS Post Closeout Runtime Monitor", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Monitor Items"), () => {
            frappe.set_route("List", "NDIS Post Closeout Runtime Monitor Item", {
                monitor: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Monitor Report"), () => {
            frappe.set_route("query-report", "NDIS Post Closeout Runtime Monitor Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Post Closeout Runtime Monitor Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 11N Baseline"), () => {
                frappe.set_route("Form", "NDIS Post Closeout Steady Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.monitor_active) {
            frm.dashboard.set_headline_alert(
                __("Post-closeout runtime monitor active. Next controlled-cycle planning gate can proceed."),
                "green"
            );
        }
    }
});
