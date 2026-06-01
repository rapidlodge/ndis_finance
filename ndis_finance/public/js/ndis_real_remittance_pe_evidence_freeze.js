frappe.ui.form.on("NDIS Real Remittance PE Evidence Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Evidence Freeze Item", {
                evidence_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Evidence Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Evidence Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 6G Rollback"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Phase 6F Smoke"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Smoke Run", frm.doc.smoke_run);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting Evidence"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Accounting Evidence"));
        }
    }
});
