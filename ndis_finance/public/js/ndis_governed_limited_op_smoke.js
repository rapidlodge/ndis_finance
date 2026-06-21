frappe.ui.form.on("NDIS Governed Limited Op Smoke", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Items"), () => {
            frappe.set_route("List", "NDIS Governed Limited Op Smoke Item", {
                smoke: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Governed Limited Op Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Phase 10V Execution Gate"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Exec Gate", frm.doc.execution_gate);
            }, __("Evidence"));
        }

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Phase 10U Preview"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Preview", frm.doc.preview);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Created Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke_completed && frm.doc.rollback_required) {
            frm.dashboard.set_headline_alert(
                __("Governed smoke completed. Rollback required immediately in Phase 10X."),
                "red"
            );
        }
    }
});
