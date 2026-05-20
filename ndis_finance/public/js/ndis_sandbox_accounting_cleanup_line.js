frappe.ui.form.on("NDIS Sandbox Accounting Cleanup Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.cleanup_run) {
            frm.add_custom_button(__("Open Cleanup Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Accounting Cleanup Run", frm.doc.cleanup_run);
            }, __("Open"));
        }

        if (frm.doc.sandbox_run) {
            frm.add_custom_button(__("Open Sandbox Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Accounting Posting Run", frm.doc.sandbox_run);
            }, __("Open"));
        }

        if (frm.doc.journal_entry && frm.doc.journal_entry_exists_after) {
            frm.add_custom_button(__("Open Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("Open"));
        }
    }
});
