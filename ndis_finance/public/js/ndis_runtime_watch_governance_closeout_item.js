frappe.ui.form.on("NDIS Runtime Watch Governance Closeout Item", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.governance_closeout) {
            frm.add_custom_button(__("Open Governance Closeout"), () => {
                frappe.set_route("Form", "NDIS Runtime Watch Governance Closeout", frm.doc.governance_closeout);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Source"));
        }
    }
});
