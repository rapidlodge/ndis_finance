frappe.ui.form.on("NDIS Funding Leakage Register", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        if (frm.doc.recovery_case) {
            frm.add_custom_button(__("Open Recovery Case"), () => {
                frappe.set_route("Form", "NDIS Recovery Case", frm.doc.recovery_case);
            }, __("Open"));
        } else if (["Open", "In Review"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Create Recovery Case"), () => {
                frappe.call({
                    method: "ndis_finance.services.recovery_engine.create_recovery_case_from_leakage",
                    args: {
                        funding_leakage: frm.doc.name,
                    },
                    freeze: true,
                    freeze_message: __("Creating recovery case..."),
                    callback(r) {
                        frm.reload_doc();

                        if (r.message && r.message.recovery_case) {
                            frappe.set_route("Form", "NDIS Recovery Case", r.message.recovery_case);
                        }
                    },
                });
            }, __("NDIS Actions"));
        }

        if (frm.doc.claim_line) {
            frm.add_custom_button(__("Open Claim Line"), () => {
                frappe.set_route("Form", "NDIS Claim Line", frm.doc.claim_line);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }

        if (frm.doc.payment_reconciliation_batch) {
            frm.add_custom_button(__("Open Reconciliation Batch"), () => {
                frappe.set_route(
                    "Form",
                    "NDIS Payment Reconciliation Batch",
                    frm.doc.payment_reconciliation_batch
                );
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source Record"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }
    },
});
