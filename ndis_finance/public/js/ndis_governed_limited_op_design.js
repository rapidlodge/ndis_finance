frappe.ui.form.on("NDIS Governed Limited Op Design", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Design Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Design Item", {
                design: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Design Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Design Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Design Guardrail Report");
        }, __("Open"));

        if (frm.doc.planning) {
            frm.add_custom_button(__("Open Phase 11D Planning"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Planning", frm.doc.planning);
            }, __("Evidence"));
        }

        if (frm.doc.precheck) {
            frm.add_custom_button(__("Open Phase 11C Precheck"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Precheck", frm.doc.precheck);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.design_approved) {
            frm.dashboard.set_headline_alert(
                __("Next governed limited operation design approved. Candidate selection can proceed."),
                "green"
            );
        }
    }
});
