frappe.ui.form.on("NDIS Next Governed Limited Op Runtime Monitor", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Runtime Monitor Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Runtime Monitor Item", {
                monitor: frm.doc.name
            });
        }, __("Open"));

        const is_phase13w = frm.doc.monitor_payment_entry === "ACC-PAY-2026-00015";

        frm.add_custom_button(__(is_phase13w ? "Open Phase 13W Runtime Monitor Report" : "Open Runtime Monitor Report"), () => {
            frappe.set_route("query-report", is_phase13w ? "NDIS Next Governed Limited Op Runtime Monitor Phase13W Report" : "NDIS Next Governed Limited Op Runtime Monitor Report");
        }, __("Open"));

        frm.add_custom_button(__(is_phase13w ? "Open Phase 13W Guardrail Report" : "Open Guardrail Report"), () => {
            frappe.set_route("query-report", is_phase13w ? "NDIS Next Governed Limited Op Runtime Monitor Phase13W Guardrail Report" : "NDIS Next Governed Limited Op Runtime Monitor Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__(is_phase13w ? "Open Phase 13V Steady Baseline" : "Open Phase 13J Baseline"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Steady Baseline", frm.doc.baseline);
            }, __("Evidence"));
        }

        if (frm.doc.gated_payment_entry) {
            frm.add_custom_button(__("Open Gated Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.gated_payment_entry);
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
