frappe.ui.form.on("NDIS Claim Batch", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Open Claim Lines"), () => {
            frappe.set_route("List", "NDIS Claim Line", {
                claim_batch: frm.doc.name,
            });
        }, __("NDIS Actions"));

        frm.add_custom_button(__("Recalculate Totals"), () => {
            frappe.call({
                method: "ndis_finance.services.claim_batch_engine.recalculate_claim_batch_totals",
                args: {
                    claim_batch: frm.doc.name,
                },
                freeze: true,
                freeze_message: __("Recalculating claim batch totals..."),
                callback() {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Claim batch totals recalculated"),
                        indicator: "green",
                    });
                },
            });
        }, __("NDIS Actions"));

        if (["Draft", "Ready to Claim"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Mark Submitted"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "external_batch_reference",
                            label: __("External Batch Reference"),
                            fieldtype: "Data",
                            reqd: 1,
                        },
                    ],
                    (values) => {
                        frappe.call({
                            method: "ndis_finance.services.claim_batch_engine.mark_claim_batch_submitted",
                            args: {
                                claim_batch: frm.doc.name,
                                external_batch_reference: values.external_batch_reference,
                            },
                            freeze: true,
                            freeze_message: __("Marking claim batch submitted..."),
                            callback() {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Claim batch marked as submitted"),
                                    indicator: "green",
                                });
                            },
                        });
                    },
                    __("Mark Claim Batch Submitted"),
                    __("Submit")
                );
            }, __("NDIS Actions"));
        }

        frm.add_custom_button(__("Open Payment Reconciliations"), () => {
            frappe.set_route("List", "NDIS Payment Reconciliation Batch", {
                claim_batch: frm.doc.name,
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Recovery Cases"), () => {
            frappe.set_route("List", "NDIS Recovery Case", {
                claim_batch: frm.doc.name,
            });
        }, __("Open"));
    },
});
