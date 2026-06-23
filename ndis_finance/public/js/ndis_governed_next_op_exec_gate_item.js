frappe.ui.form.on("NDIS Governed Next Op Exec Gate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.execution_gate) {
            frm.add_custom_button(__("Open Execution Gate"), () => {
                frappe.set_route("Form", "NDIS Governed Next Op Exec Gate", frm.doc.execution_gate);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
