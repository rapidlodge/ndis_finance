frappe.ui.form.on("NDIS Real Remittance Batch PE Rollback Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch PE Rollback Line", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Phase 7F Smoke"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch PE Smoke Run", frm.doc.smoke_run);
            }, __("Evidence"));
        }
    }
});
