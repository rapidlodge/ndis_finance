frappe.ui.form.on("NDIS Claim Line", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }

        if (frm.doc.claim_batch) {
            frm.add_custom_button(__("Open Claim Batch"), () => {
                frappe.set_route("Form", "NDIS Claim Batch", frm.doc.claim_batch);
            }, __("Open"));
        }

        if (frm.doc.reconciliation_batch) {
            frm.add_custom_button(__("Open Reconciliation Batch"), () => {
                frappe.set_route(
                    "Form",
                    "NDIS Payment Reconciliation Batch",
                    frm.doc.reconciliation_batch
                );
            }, __("Open"));
        }

        if (frm.doc.recovery_case) {
            frm.add_custom_button(__("Open Recovery Case"), () => {
                frappe.set_route("Form", "NDIS Recovery Case", frm.doc.recovery_case);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Related Leakage"), () => {
            frappe.set_route("List", "NDIS Funding Leakage Register", {
                claim_line: frm.doc.name,
            });
        }, __("Open"));

        if (["Short Paid", "Rejected", "Reclaim Required"].includes(frm.doc.claim_status)) {
            frm.add_custom_button(__("Open / Create Recovery Case"), () => {
                if (frm.doc.recovery_case) {
                    frappe.set_route("Form", "NDIS Recovery Case", frm.doc.recovery_case);
                    return;
                }

                frappe.set_route("List", "NDIS Funding Leakage Register", {
                    claim_line: frm.doc.name,
                });
            }, __("NDIS Actions"));
        }
    },
});
