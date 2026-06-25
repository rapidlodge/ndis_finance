frappe.ui.form.on("NDIS Governed Next Op Rollback Freeze Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Freeze"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Rollback Freeze", frm.doc.freeze);
            }, __("Open"));
        }

        if (frm.doc.rolled_back_payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.rolled_back_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
