frappe.ui.form.on("NDIS Real Remittance PE Adapter Run Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.adapter_run) {
            frm.add_custom_button(__("Open Adapter Run"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Adapter Run", frm.doc.adapter_run);
            }, __("Open"));
        }

        if (frm.doc.preview_line) {
            frm.add_custom_button(__("Open Preview Line"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Preview Line", frm.doc.preview_line);
            }, __("Evidence"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Evidence"));
        }

        if (frm.doc.claim_line) {
            frm.add_custom_button(__("Open Claim Line"), () => {
                frappe.set_route("Form", "NDIS Claim Line", frm.doc.claim_line);
            }, __("Evidence"));
        }
    }
});
