frappe.ui.form.on("NDIS Sandbox Payment Entry Run Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.sandbox_run) {
            frm.add_custom_button(__("Open Sandbox Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Payment Entry Run", frm.doc.sandbox_run);
            }, __("Open"));
        }

        if (frm.doc.allocation_preview_line) {
            frm.add_custom_button(__("Open Preview Line"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Allocation Preview Line", frm.doc.allocation_preview_line);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }
    }
});
