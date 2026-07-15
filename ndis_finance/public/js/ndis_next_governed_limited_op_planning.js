frappe.ui.form.on("NDIS Next Governed Limited Op Planning", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Planning Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Planning Item", {
                planning: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Planning Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Planning Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13L Planning Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Planning Phase13L Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Planning Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13L Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Planning Phase13L Guardrail Report");
        }, __("Open"));

        if (frm.doc.monitor) {
            frm.add_custom_button(__("Open Phase 13K Runtime Monitor"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Runtime Monitor", frm.doc.monitor);
            }, __("Evidence"));
        }

        if (frm.doc.planning_payment_entry || frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Planned Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.planning_payment_entry || frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.planning_approved) {
            frm.dashboard.set_headline_alert(
                __("Governed limited-operation planning approved. Design gate can proceed next."),
                "green"
            );
        }
    }
});
