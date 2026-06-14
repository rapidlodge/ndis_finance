frappe.ui.form.on("NDIS Single Guarded Limited Operation Smoke", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Items"), () => {
            frappe.set_route("List", "NDIS Single Guarded Limited Operation Smoke Item", {
                smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Single Guarded Limited Operation Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Single Guarded Limited Operation Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Created Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Phase 10I Gate"), () => {
                frappe.set_route("Form", "NDIS Guarded Limited Operation Execution Gate", frm.doc.execution_gate);
            }, __("Evidence"));
        }

        if (frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Smoke completed. Rollback is required immediately in Phase 10K."),
                "orange"
            );
        }
    }
});