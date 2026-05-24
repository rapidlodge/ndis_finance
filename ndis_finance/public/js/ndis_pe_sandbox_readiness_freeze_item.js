frappe.ui.form.on("NDIS PE Sandbox Readiness Freeze Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.readiness_freeze) {
            frm.add_custom_button(__("Open Readiness Freeze"), () => {
                frappe.set_route("Form", "NDIS PE Sandbox Readiness Freeze", frm.doc.readiness_freeze);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
