frappe.ui.form.on("NDIS Claim Export Line", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        if (frm.doc.claim_export) {
            frm.add_custom_button(__("Open Claim Export"), () => {
                frappe.set_route("Form", "NDIS Claim Export", frm.doc.claim_export);
            }, __("Open"));
        }

        if (frm.doc.claim_line) {
            frm.add_custom_button(__("Open Claim Line"), () => {
                frappe.set_route("Form", "NDIS Claim Line", frm.doc.claim_line);
            }, __("Open"));
        }

        if (frm.doc.claim_batch) {
            frm.add_custom_button(__("Open Claim Batch"), () => {
                frappe.set_route("Form", "NDIS Claim Batch", frm.doc.claim_batch);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }
    },
});
