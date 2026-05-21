frappe.ui.form.on("NDIS Payment Entry Sandbox Completion Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.completion_gate) {
            frm.add_custom_button(__("Open Completion Gate"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Sandbox Completion Gate", frm.doc.completion_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    }
});
