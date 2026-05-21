frappe.ui.form.on("NDIS Sandbox Payment Entry Cleanup Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.cleanup_run) {
            frm.add_custom_button(__("Open Cleanup Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Payment Entry Cleanup Run", frm.doc.cleanup_run);
            }, __("Open"));
        }

        if (frm.doc.sandbox_run) {
            frm.add_custom_button(__("Open Sandbox Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Payment Entry Run", frm.doc.sandbox_run);
            }, __("Open"));
        }

        if (frm.doc.payment_entry && frm.doc.payment_entry_exists_after) {
            frm.add_custom_button(__("Open Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Open"));
        }
    }
});
