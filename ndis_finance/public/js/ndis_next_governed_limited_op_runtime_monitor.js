frappe.ui.form.on("NDIS Next Governed Limited Op Runtime Monitor", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Runtime Monitor Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Runtime Monitor Item", {
                monitor: frm.doc.name
            });
        }, __("Open"));

        const is_phase13w = frm.doc.monitor_payment_entry === "ACC-PAY-2026-00015";
        const is_phase14i = frm.doc.monitor_payment_entry === "ACC-PAY-2026-00016";
        const monitor_report = is_phase14i
            ? "NDIS Next Governed Limited Op Runtime Monitor Phase14I Report"
            : (is_phase13w ? "NDIS Next Governed Limited Op Runtime Monitor Phase13W Report" : "NDIS Next Governed Limited Op Runtime Monitor Report");
        const guardrail_report = is_phase14i
            ? "NDIS Next Governed Limited Op Runtime Monitor Phase14I Guardrail Report"
            : (is_phase13w ? "NDIS Next Governed Limited Op Runtime Monitor Phase13W Guardrail Report" : "NDIS Next Governed Limited Op Runtime Monitor Guardrail Report");
        const phase_label = is_phase14i ? "Phase 14I" : (is_phase13w ? "Phase 13W" : "");
        const baseline_label = is_phase14i ? "Open Phase 14H Steady Baseline" : (is_phase13w ? "Open Phase 13V Steady Baseline" : "Open Phase 13J Baseline");

        frm.add_custom_button(__(phase_label ? `Open ${phase_label} Runtime Monitor Report` : "Open Runtime Monitor Report"), () => {
            frappe.set_route("query-report", monitor_report);
        }, __("Open"));

        frm.add_custom_button(__(phase_label ? `Open ${phase_label} Guardrail Report` : "Open Guardrail Report"), () => {
            frappe.set_route("query-report", guardrail_report);
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__(baseline_label), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Steady Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.previous_gated_payment_entry) {
            frm.add_custom_button(__("Open Previous Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.previous_gated_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.monitor_payment_entry || frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitor_payment_entry || frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.monitor_active) {
            frm.dashboard.set_headline_alert(
                __("Governed limited-operation runtime monitor active. Next planning gate is ready."),
                "green"
            );
        }
    }
});
