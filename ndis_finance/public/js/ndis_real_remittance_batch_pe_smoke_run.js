frappe.ui.form.on("NDIS Real Remittance Batch PE Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Lines"), () => {
            frappe.set_route("List", "NDIS Real Remittance Batch PE Smoke Line", {
                smoke_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Smoke Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Smoke Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Guardrail Report"), () => {
            frappe.set_route("query-report", "NDIS Real Remittance Batch PE Smoke Guardrail Report");
        }, __("Open"));

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.source_run) {
            frm.add_custom_button(__("Open Phase 7E Source"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch Source Harness Run", frm.doc.source_run);
            }, __("Evidence"));
        }
    }
});
