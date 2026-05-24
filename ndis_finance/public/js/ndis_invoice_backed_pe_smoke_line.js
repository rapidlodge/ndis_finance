frappe.ui.form.on("NDIS Invoice Backed PE Smoke Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.smoke_run) {
            frm.add_custom_button(__("Open Smoke Run"), () => {
                frappe.set_route("Form", "NDIS Invoice Backed PE Smoke Run", frm.doc.smoke_run);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
