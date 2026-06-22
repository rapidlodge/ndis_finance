frappe.ui.form.on("NDIS Governed Limited Op Candidate Validation Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.validation) {
            frm.add_custom_button(__("Open Validation"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Candidate Validation", frm.doc.validation);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }
    }
});
