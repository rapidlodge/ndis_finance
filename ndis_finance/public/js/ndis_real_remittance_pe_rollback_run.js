frappe.ui.form.on("NDIS Real Remittance PE Rollback Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Rollback Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance PE Rollback Line", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Rollback Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Rollback Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Line Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Rollback Line Report", {
                rollback_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrails"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance PE Rollback Guardrail Report");
        }, __("Open"));

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Phase 6F Smoke"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Smoke Run", frm.doc.smoke_run);
            }, __("Evidence"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Evidence"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Evidence"));
        }
    }
});
