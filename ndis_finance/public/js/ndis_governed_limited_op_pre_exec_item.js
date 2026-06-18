frappe.ui.form.on("NDIS Governed Limited Op Pre Exec Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.pre_execution_gate) {
            frm.add_custom_button(__("Open Pre-Execution Gate"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Pre Exec", frm.doc.pre_execution_gate);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
