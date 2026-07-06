frappe.ui.form.on("NDIS Next Governed Limited Op Closeout Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.closeout) {
            frm.add_custom_button(__("Open Closeout"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Closeout", frm.doc.closeout);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }

        if (frm.doc.closeout_payment_entry) {
            frm.add_custom_button(__("Open Closeout Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.closeout_payment_entry);
            }, __("Accounting"));
        }
    }
});
