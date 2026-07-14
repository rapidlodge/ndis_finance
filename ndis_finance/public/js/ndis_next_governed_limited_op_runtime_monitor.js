frappe.ui.form.on("NDIS Next Governed Limited Op Runtime Monitor", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Monitor Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Runtime Monitor Item", {
                monitor: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Runtime Monitor Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Runtime Monitor Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Runtime Monitor Guardrail Report");
        }, __("Open"));

        if (frm.doc.baseline) {
            frm.add_custom_button(__("Open Phase 13J Baseline"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Steady Baseline", frm.doc.baseline);
            }, __("Evidence"));
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
