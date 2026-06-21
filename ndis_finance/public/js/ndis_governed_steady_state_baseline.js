frappe.ui.form.on("NDIS Governed Steady State Baseline", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Baseline Items"), () => {
            frappe.set_route("List", "NDIS Governed Steady State Baseline Item", { baseline: frm.doc.name });
        }, __("Open"));

        frm.add_custom_button(__("Open Baseline Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Steady State Baseline Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Steady State Baseline Guardrail Report");
        }, __("Open"));

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Phase 10Z Closeout"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Closeout", frm.doc.closeout);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_active) {
            frm.dashboard.set_headline_alert(__("Governed steady-state continuation baseline is active."), "green");
        }
    }
});
