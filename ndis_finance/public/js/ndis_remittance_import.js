frappe.ui.form.on("NDIS Remittance Import", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Import Lines"), () => {
            frappe.set_route("List", "NDIS Remittance Import Line", {
                remittance_import: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.payment_reconciliation_batch) {
            frm.add_custom_button(__("Open Reconciliation Batch"), () => {
                frappe.set_route("Form", "NDIS Payment Reconciliation Batch", frm.doc.payment_reconciliation_batch);
            }, __("Open"));
        }

        if (frm.doc.claim_batch) {
            frm.add_custom_button(__("Open Claim Batch"), () => {
                frappe.set_route("Form", "NDIS Claim Batch", frm.doc.claim_batch);
            }, __("Open"));
        }

        if (["Imported", "Partially Matched", "Matched"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Match Lines"), () => {
                frappe.call({
                    method: "ndis_finance.services.remittance_importer.match_remittance_import",
                    args: {
                        remittance_import: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Matching remittance lines..."),
                    callback() {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("Remittance matching completed"),
                            indicator: "green"
                        });
                    }
                });
            }, __("NDIS Actions"));
        }

        if (["Matched", "Partially Matched"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Apply Remittance"), () => {
                frappe.confirm(
                    __("This applies remittance outcomes to NDIS reconciliation controls only. It will not create Payment Entry, Journal Entry, GL Entry, or bank allocation. Continue?"),
                    () => {
                        frappe.call({
                            method: "ndis_finance.services.remittance_importer.apply_remittance_import",
                            args: {
                                remittance_import: frm.doc.name,
                                create_reconciliation_batch: 1
                            },
                            freeze: true,
                            freeze_message: __("Applying remittance..."),
                            callback() {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Remittance applied to NDIS controls. No accounting movement created."),
                                    indicator: "green"
                                });
                            }
                        });
                    }
                );
            }, __("NDIS Actions"));
        }
    }
});
