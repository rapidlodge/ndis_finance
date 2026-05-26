frappe.ui.form.on("NDIS PE Submitted Smoke Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.submitted_smoke_gate) {
            frm.add_custom_button(__("Open Submitted Smoke Gate"), () => {
                frappe.set_route("Form", "NDIS PE Submitted Smoke Gate", frm.doc.submitted_smoke_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
