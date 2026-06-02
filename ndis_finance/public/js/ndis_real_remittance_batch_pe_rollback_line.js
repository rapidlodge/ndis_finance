frappe.ui.form.on("NDIS Real Remittance Batch PE Rollback Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rollback_run) {
            frm.add_custom_button(__("Open Rollback Run"), () => {
                frappe.set_route("Form", "NDIS Real Remittance Batch PE Rollback Run", frm.doc.rollback_run);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }
    }
});
