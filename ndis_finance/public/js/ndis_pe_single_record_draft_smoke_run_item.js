frappe.ui.form.on("NDIS PE Single Record Draft Smoke Run Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Smoke Run"), () => {
                frappe.set_route("Form", "NDIS PE Single Record Draft Smoke Run", frm.doc.smoke_run);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
