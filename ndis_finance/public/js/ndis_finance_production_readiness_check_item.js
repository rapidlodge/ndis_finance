frappe.ui.form.on("NDIS Finance Production Readiness Check Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.readiness_check) {
            frm.add_custom_button(__("Open Readiness Check"), () => {
                frappe.set_route("Form", "NDIS Finance Production Readiness Check", frm.doc.readiness_check);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
