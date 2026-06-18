frappe.ui.form.on("NDIS Governed Limited Ops Readiness Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.readiness) {
            frm.add_custom_button(__("Open Readiness"), () => {
                frappe.set_route("Form", "NDIS Governed Limited Ops Readiness", frm.doc.readiness);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
