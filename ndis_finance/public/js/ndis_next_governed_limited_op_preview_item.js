frappe.ui.form.on("NDIS Next Governed Limited Op Preview Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Preview"), () => {
                frappe.set_route("Form", "NDIS Next Governed Limited Op Preview", frm.doc.preview);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }

        if (frm.doc.monitored_payment_entry) {
            frm.add_custom_button(__("Open Monitored Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.monitored_payment_entry);
            }, __("Accounting"));
        }
    }
});
