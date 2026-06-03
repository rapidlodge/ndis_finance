frappe.ui.form.on("NDIS Controlled Production Batch Smoke Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Smoke Run"), () => {
                frappe.set_route("Form", "NDIS Controlled Production Batch Smoke Run", frm.doc.smoke_run);
            }, __("Open"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }
    }
});
