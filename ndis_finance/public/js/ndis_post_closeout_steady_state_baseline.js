frappe.ui.form.on("NDIS Post Closeout Steady Baseline", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Baseline Items"), () => {
            frappe.set_route("List", "NDIS Post Closeout Steady Baseline Item", {
                baseline: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Baseline Report"), () => {
            frappe.set_route("query-report", "NDIS Post Closeout Steady Baseline Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Post Closeout Steady Baseline Guardrail Report");
        }, __("Open"));

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Phase 11M Closeout"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Closeout", frm.doc.closeout);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.baseline_active) {
            frm.dashboard.set_headline_alert(
                __("Post-closeout steady-state baseline active. Monitoring and next-cycle planning can proceed."),
                "green"
            );
        }
    }
});
