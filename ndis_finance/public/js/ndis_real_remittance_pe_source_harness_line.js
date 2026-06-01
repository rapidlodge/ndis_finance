frappe.ui.form.on("NDIS Real Remittance PE Source Harness Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.harness_run) {
            frm.add_custom_button(__("Open Harness Run"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Source Harness Run", frm.doc.harness_run);
            }, __("Open"));
        }

        if (frm.doc.record_doctype && frm.doc.record_name) {
            frm.add_custom_button(__("Open Source Record"), () => {
                frappe.set_route("Form", frm.doc.record_doctype, frm.doc.record_name);
            }, __("Open"));
        }
    }
});
