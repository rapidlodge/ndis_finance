frappe.ui.form.on("NDIS Next Controlled Cycle Planning", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Planning Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Plan Item", {
                planning: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Planning Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Planning Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Planning Guardrail Report");
        }, __("Open"));

        if (frm.doc.monitor) {
            frm.add_custom_button(__("Open Phase 11O Monitor"), () => {
                frappe.set_route("Form", "NDIS Post Closeout Runtime Monitor", frm.doc.monitor);
            }, __("Evidence"));
        }

        if (frm.doc.baseline_payment_entry) {
            frm.add_custom_button(__("Open Baseline Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.baseline_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.planning_approved) {
            frm.dashboard.set_headline_alert(
                __("Next controlled-cycle planning approved. Design gate can proceed; candidate selection has not started."),
                "green"
            );
        }
    }
});
