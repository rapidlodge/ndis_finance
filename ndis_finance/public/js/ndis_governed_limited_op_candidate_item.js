frappe.ui.form.on("NDIS Governed Limited Op Candidate Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.candidate) {
            frm.add_custom_button(__("Open Candidate Selection"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Op Candidate", frm.doc.candidate);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Reference"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
