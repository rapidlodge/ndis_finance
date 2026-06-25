frappe.ui.form.on("NDIS Governed Next Op Closeout Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Closeout"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Closeout", frm.doc.closeout);
            }, __("Open"));
        }

        if (frm.doc.closed_payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.closed_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
