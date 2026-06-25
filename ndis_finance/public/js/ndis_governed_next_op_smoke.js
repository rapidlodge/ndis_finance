frappe.ui.form.on("NDIS Governed Next Op Smoke", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Items"), () => {
            frappe.set_route("List", "NDIS Governed Next Op Smoke Item", {
                smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Next Op Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Phase 11I Gate"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Exec Gate", frm.doc.execution_gate);
            }, __("Evidence"));
        }

        if (frm.doc.created_payment_entry) {
            frm.add_custom_button(__("Open Created Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.created_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Smoke completed. Rollback is required before proceeding."),
                "orange"
            );
        }
    }
});
