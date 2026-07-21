frappe.ui.form.on("NDIS Next Governed Limited Op Steady Baseline", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Steady Baseline Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Steady Baseline Item", {baseline: frm.doc.name});
        }, __("Open"));

        frm.add_custom_button(__("Open Baseline Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Steady Baseline Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Steady Baseline Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline_payment_entry === "ACC-PAY-2026-00015") {
            frm.add_custom_button(__("Open Phase 13V Steady Baseline Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Steady Baseline Phase13V Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 13V Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Steady Baseline Phase13V Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.baseline_payment_entry === "ACC-PAY-2026-00016") {
            frm.add_custom_button(__("Open Phase 14H Steady Baseline Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Steady Baseline Phase14H Report");
            }, __("Open"));

            frm.add_custom_button(__("Open Phase 14H Guardrail Report"), () => {
                frappe.set_route("query-report", "NDIS Next Governed Limited Op Steady Baseline Phase14H Guardrail Report");
            }, __("Open"));
        }

        if (frm.doc.closeout) {
            const closeoutLabel = frm.doc.baseline_payment_entry === "ACC-PAY-2026-00016"
                ? "Open Phase 14G Closeout"
                : frm.doc.baseline_payment_entry === "ACC-PAY-2026-00015"
                    ? "Open Phase 13U Closeout"
                    : "Open Phase 13I Closeout";
            frm.add_custom_button(__(closeoutLabel), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Closeout", frm.doc.closeout);
            }, __("Evidence"));
        }

        if (frm.doc.previous_gated_payment_entry) {
            frm.add_custom_button(__("Open Previous Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.baseline_active) {
            frm.dashboard.set_headline_alert(__("Governed limited-operation steady-state baseline active. Runtime monitor can proceed next."), "green");
        }
    }
});
