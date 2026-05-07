frappe.ui.form.on("NDIS Payment Reconciliation Batch", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Open Reconciliation Lines"), () => {
            frappe.set_route("List", "NDIS Payment Reconciliation Line", {
                reconciliation_batch: frm.doc.name,
            });
        }, __("Open"));

        if (frm.doc.claim_batch) {
            frm.add_custom_button(__("Open Claim Batch"), () => {
                frappe.set_route("Form", "NDIS Claim Batch", frm.doc.claim_batch);
            }, __("Open"));

            frm.add_custom_button(__("Open Claim Lines"), () => {
                frappe.set_route("List", "NDIS Claim Line", {
                    claim_batch: frm.doc.claim_batch,
                });
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Funding Leakage"), () => {
            frappe.set_route("List", "NDIS Funding Leakage Register", {
                payment_reconciliation_batch: frm.doc.name,
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Recovery Cases"), () => {
            frappe.set_route("List", "NDIS Recovery Case", {
                payment_reconciliation_batch: frm.doc.name,
            });
        }, __("Open"));

        frm.add_custom_button(__("Recalculate Totals"), () => {
            frappe.call({
                method: "ndis_finance.services.payment_reconciliation_engine.recalculate_payment_reconciliation_batch",
                args: {
                    reconciliation_batch: frm.doc.name,
                },
                freeze: true,
                freeze_message: __("Recalculating payment reconciliation totals..."),
                callback() {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Payment reconciliation totals recalculated"),
                        indicator: "green",
                    });
                },
            });
        }, __("NDIS Actions"));
    },
});
