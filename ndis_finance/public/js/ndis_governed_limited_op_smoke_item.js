frappe.ui.form.on("NDIS Governed Limited Op Smoke Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Smoke"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Smoke", frm.doc.smoke);
            }, __("Open"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
