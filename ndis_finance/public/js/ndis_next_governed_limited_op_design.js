frappe.ui.form.on("NDIS Next Governed Limited Op Design", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Design Items"), () => {
            frappe.set_route("List", "NDIS Next Governed Limited Op Design Item", {
                design: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Design Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Design Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13M Design Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Design Phase13M Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Design Guardrail Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Phase 13M Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Governed Limited Op Design Phase13M Guardrail Report");
        }, __("Open"));

        if (frm.doc.planning) {
            frm.add_custom_button(__("Open Phase 13L Planning"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Planning", frm.doc.planning);
            }, __("Evidence"));
        }

        if (frm.doc.monitor) {
            frm.add_custom_button(__("Open Phase 12Y Runtime Monitor"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Runtime Monitor", frm.doc.monitor);
            }, __("Evidence"));
        }

        if (frm.doc.design_payment_entry || frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Designed Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.design_payment_entry || frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.design_approved) {
            frm.dashboard.set_headline_alert(
                __("Governed limited-operation design approved. Candidate selection gate can proceed next."),
                "green"
            );
        }
    }
});
