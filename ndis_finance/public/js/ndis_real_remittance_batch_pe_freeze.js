frappe.ui.form.on("NDIS Real Remittance Batch PE Evidence Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch PE Evidence Freeze Item", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Freeze Item Report", {
                freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrails"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Freeze Guardrail Report");
        }, __("Open"));

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Phase 7G Rollback"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch PE Rollback Run", frm.doc.rollback_run);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }
    }
});
