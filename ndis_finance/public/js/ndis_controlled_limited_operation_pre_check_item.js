frappe.ui.form.on("NDIS Controlled Limited Operation Pre Check Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.pre_check) {
            frm.add_custom_button(__("Open Pre Check"), () => {
                frappe.set_route("Form", "NDIS Controlled Limited Operation Pre Check", frm.doc.pre_check);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});