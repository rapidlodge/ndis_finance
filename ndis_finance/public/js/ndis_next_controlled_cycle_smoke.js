frappe.ui.form.on("NDIS Next Controlled Cycle Smoke", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Items"), () => {
            frappe.set_route("List", "NDIS Next Controlled Cycle Smoke Item", {
                smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Next Controlled Cycle Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Phase 11U Execution Gate"), () => {
                frappe.set_route("Form", "NDIS Next Controlled Cycle Exec Gate", frm.doc.execution_gate);
            }, __("Evidence"));
        }

        if (frm.doc.created_payment_entry) {
            frm.add_custom_button(__("Open Created Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.created_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke_completed) {
            frm.dashboard.set_headline_alert(
                __("Controlled smoke completed. Rollback is mandatory before freeze or closeout."),
                "orange"
            );
        }
    }
});
