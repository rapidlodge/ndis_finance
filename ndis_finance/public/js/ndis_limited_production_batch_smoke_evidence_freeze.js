frappe.ui.form.on("NDIS Limited Production Batch Smoke Evidence Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Limited Production Batch Smoke Evidence Freeze Item", {
                evidence_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Smoke Evidence Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Limited Production Batch Smoke Evidence Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 9G Rollback"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Smoke Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Phase 9F Smoke"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Smoke Run", frm.doc.smoke_run);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Cancelled Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.ready_for_next_phase) {
            frm.dashboard.set_headline_alert(
                __("Evidence frozen. Ready for limited production batch policy finalisation."),
                "green"
            );
        }
    }
});