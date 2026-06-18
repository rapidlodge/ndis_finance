frappe.ui.form.on("NDIS Runtime Watch Violation Sim Freeze Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.freeze) {
            frm.add_custom_button(__("Open Freeze"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Violation Sim Freeze", frm.doc.freeze);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
