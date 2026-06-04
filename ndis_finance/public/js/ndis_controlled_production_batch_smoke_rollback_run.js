frappe.ui.form.on("NDIS Controlled Production Batch Smoke Rollback Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Lines"), () => {
            frappe.set_route("List", "NDIS Controlled Production Batch Smoke Rollback Line", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Smoke Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Controlled Production Batch Smoke Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Phase 8E Smoke"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Smoke Run", frm.doc.smoke_run);
            }, __("Evidence"));
        }

        if (frm.doc.ready_for_freeze) {
            frm.dashboard.set_headline_alert(
                __("Rollback completed. Create Phase 8G freeze evidence before any further production movement."),
                "green"
            );
        }
    }
});