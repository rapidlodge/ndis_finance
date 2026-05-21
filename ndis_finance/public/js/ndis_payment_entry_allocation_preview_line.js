frappe.ui.form.on("NDIS Payment Entry Allocation Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.allocation_preview) {
            frm.add_custom_button(__("Open Allocation Preview"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Allocation Preview", frm.doc.allocation_preview);
            }, __("Open"));
        }

        if (frm.doc.remittance_line) {
            frm.add_custom_button(__("Open Remittance Line"), () => {
                frappe.set_route("Form", "NDIS Remittance Import Line", frm.doc.remittance_line);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }
    }
});
