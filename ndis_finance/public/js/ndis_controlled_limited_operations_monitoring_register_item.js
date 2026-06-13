frappe.ui.form.on("NDIS Controlled Limited Operations Monitoring Register Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.register) {
            frm.add_custom_button(__("Open Register"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operations Monitoring Register", frm.doc.register);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
