frappe.ui.form.on("NDIS PE Live Smoke Completion Freeze Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.completion_freeze) {
            frm.add_custom_button(__("Open Completion Freeze"), () => {
                frappe.set_route("Form", "NDIS PE Live Smoke Completion Freeze", frm.doc.completion_freeze);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
