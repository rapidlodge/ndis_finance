frappe.ui.form.on("NDIS Next Post Closeout Steady Baseline", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Baseline Items"), () => {
            frappe.set_route("List", "NDIS Next Post Closeout Steady Baseline Item", {
                baseline: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Baseline Report"), () => {
            frappe.set_route("query-report", "NDIS Next Post Closeout Steady Baseline Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Post Closeout Steady Baseline Guardrail Report");
        }, __("Open"));

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Phase 11Y Closeout"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Closeout", frm.doc.closeout);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.baseline_active) {
            frm.dashboard.set_headline_alert(
                __("Next post-closeout steady-state baseline is active. Monitoring can proceed next."),
                "green"
            );
        }
    }
});
