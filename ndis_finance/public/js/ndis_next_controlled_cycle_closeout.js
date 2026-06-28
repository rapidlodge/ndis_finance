frappe.ui.form.on("NDIS Next Controlled Cycle Closeout", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Closeout Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Closeout Item", {
                closeout: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Closeout Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Closeout Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Closeout Guardrail Report");
        }, __("Open"));

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Phase 11X Freeze"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Rollback Freeze", frm.doc.freeze);
            }, __("Evidence"));
        }

        if (frm.doc.closed_payment_entry) {
            frm.add_custom_button(__("Open Closed Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.closed_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.closeout_approved) {
            frm.dashboard.set_headline_alert(
                __("Next controlled-cycle smoke is closed. Steady-state baseline can proceed next."),
                "green"
            );
        }
    }
});
