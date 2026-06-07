frappe.ui.form.on("NDIS Limited Production Batch Adapter Run Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.adapter_run) {
            frm.add_custom_button(__("Open Adapter Run"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Adapter Run", frm.doc.adapter_run);
            }, __("Open"));
        }

        if (frm.doc.policy_preview_line) {
            frm.add_custom_button(__("Open Policy Preview Line"), () => {
                frappe.set_route("Form", "NDIS Limited Production Batch Policy Preview Line", frm.doc.policy_preview_line);
            }, __("Source"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Source"));
        }
    }
});
