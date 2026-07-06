frappe.ui.form.on("NDIS Next Governed Limited Op Rollback Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rollback) {
            frm.add_custom_button(__("Open Rollback"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Rollback", frm.doc.rollback);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }

        if (frm.doc.rollback_payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.rollback_payment_entry);
            }, __("Accounting"));
        }
    }
});
