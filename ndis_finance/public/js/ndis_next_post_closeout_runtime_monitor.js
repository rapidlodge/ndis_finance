frappe.ui.form.on("NDIS Next Post Closeout Runtime Monitor", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Monitor Items"), () => {
            frappe.set_route("List", "NDIS Next Post Closeout Runtime Monitor Item", {
                monitor: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Monitor Report"), () => {
            frappe.set_route("query-report", "NDIS Next Post Closeout Runtime Monitor Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Post Closeout Runtime Monitor Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 11Z Baseline"), () => {
                frappe.set_route("Form", "NDIS Next Post Closeout Steady Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.monitor_active) {
            frm.dashboard.set_headline_alert(
                __("Next post-closeout runtime monitor is active. Governed limited-operation planning can proceed next."),
                "green"
            );
        }
    }
});
