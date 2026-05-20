frappe.ui.form.on("NDIS Sandbox Accounting Posting Run Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.sandbox_run) {
            frm.add_custom_button(__("Open Sandbox Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Accounting Posting Run", frm.doc.sandbox_run);
            }, __("Open"));
        }

        if (frm.doc.posting_request_line) {
            frm.add_custom_button(__("Open Request Line"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Request Line", frm.doc.posting_request_line);
            }, __("Open"));
        }

        if (frm.doc.reference_doctype && frm.doc.reference_name) {
            frm.add_custom_button(__("Open Reference"), () => {
                frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
            }, __("Open"));
        }
    }
});
