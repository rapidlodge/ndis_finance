frappe.ui.form.on("NDIS Real Remittance PE Preview Line", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.preview) {
            frm.add_custom_button(__("Open Preview"), () => {
                frappe.set_route("Form", "NDIS Real Remittance PE Preview", frm.doc.preview);
            }, __("Open"));
        }

        if (frm.doc.source_remittance_line) {
            frm.add_custom_button(__("Open Remittance Line"), () => {
                frappe.set_route("Form", "NDIS Remittance Import Line", frm.doc.source_remittance_line);
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
