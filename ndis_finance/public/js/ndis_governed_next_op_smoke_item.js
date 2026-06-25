frappe.ui.form.on("NDIS Governed Next Op Smoke Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.smoke) {
            frm.add_custom_button(__("Open Smoke"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Smoke", frm.doc.smoke);
            }, __("Open"));
        }

        if (frm.doc.created_payment_entry) {
            frm.add_custom_button(__("Open Created Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.created_payment_entry);
            }, __("Accounting"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
