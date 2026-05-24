frappe.ui.form.on("NDIS Sandbox Invoice Test Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.test_run) {
            frm.add_custom_button(__("Open Test Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Invoice Test Run", frm.doc.test_run);
            }, __("Open"));
        }

        if (frm.doc.record_doctype && frm.doc.record_name) {
            frm.add_custom_button(__("Open Source Record"), () => {
                frappe.set_route("Form", frm.doc.record_doctype, frm.doc.record_name);
            }, __("Open"));
        }
    }
});
