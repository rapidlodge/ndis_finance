frappe.ui.form.on("NDIS Remittance Import Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.remittance_import) {
            frm.add_custom_button(__("Open Remittance Import"), () => {
                frappe.set_route("Form", "NDIS Remittance Import", frm.doc.remittance_import);
            }, __("Open"));
        }

        if (frm.doc.matched_claim_line) {
            frm.add_custom_button(__("Open Claim Line"), () => {
                frappe.set_route("Form", "NDIS Claim Line", frm.doc.matched_claim_line);
            }, __("Open"));
        }

        if (frm.doc.payment_reconciliation_line) {
            frm.add_custom_button(__("Open Reconciliation Line"), () => {
                frappe.set_route("Form", "NDIS Payment Reconciliation Line", frm.doc.payment_reconciliation_line);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }
    }
});
