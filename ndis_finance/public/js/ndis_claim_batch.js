frappe.ui.form.on("NDIS Claim Batch", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Open Claim Lines"), () => {
            frappe.set_route("List", "NDIS Claim Line", {
                claim_batch: frm.doc.name,
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Claim Exports"), () => {
            frappe.set_route("List", "NDIS Claim Export", {
                claim_batch: frm.doc.name,
            });
        }, __("Open"));

        if (frm.doc.last_claim_export) {
            frm.add_custom_button(__("Open Last Claim Export"), () => {
                frappe.set_route("Form", "NDIS Claim Export", frm.doc.last_claim_export);
            }, __("Open"));
        }

        frm.add_custom_button(__("Preview Claim Export"), () => {
            frappe.call({
                method: "ndis_finance.services.claim_exporter.preview_claim_export",
                args: {
                    claim_batch: frm.doc.name,
                    export_type: "NDIA Claim CSV",
                },
                freeze: true,
                freeze_message: __("Previewing claim export..."),
                callback(r) {
                    const msg = r.message || {};
                    frappe.msgprint({
                        title: __("Claim Export Preview"),
                        message: __("Eligible Lines: {0}<br>Total Claim Amount: {1}", [
                            msg.line_count || 0,
                            format_currency(msg.total_claim_amount || 0),
                        ]),
                        indicator: "blue",
                    });
                },
            });
        }, __("Claim Export"));

        frm.add_custom_button(__("Generate Claim Export CSV"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "export_type",
                        label: __("Export Type"),
                        fieldtype: "Select",
                        options: "\nNDIA Claim CSV\nPlan Manager CSV\nSelf Managed CSV\nInternal Review CSV",
                        default: "NDIA Claim CSV",
                        reqd: 1,
                    },
                    {
                        fieldname: "include_submitted",
                        label: __("Include Submitted Lines"),
                        fieldtype: "Check",
                        default: 0,
                    },
                    {
                        fieldname: "include_exported",
                        label: __("Include Already Exported Lines"),
                        fieldtype: "Check",
                        default: 0,
                    },
                ],
                (values) => {
                    frappe.confirm(
                        __("This generates an internal CSV export file only. It does not submit to NDIA and does not create accounting entries. Continue?"),
                        () => {
                            frappe.call({
                                method: "ndis_finance.services.claim_exporter.generate_claim_export",
                                args: {
                                    claim_batch: frm.doc.name,
                                    export_type: values.export_type,
                                    include_submitted: values.include_submitted,
                                    include_exported: values.include_exported,
                                },
                                freeze: true,
                                freeze_message: __("Generating claim export..."),
                                callback(r) {
                                    frm.reload_doc();

                                    if (r.message && r.message.claim_export) {
                                        frappe.show_alert({
                                            message: __("Claim export generated. No external submission or accounting movement created."),
                                            indicator: "green",
                                        });
                                        frappe.set_route("Form", "NDIS Claim Export", r.message.claim_export);
                                    } else {
                                        frappe.msgprint(
                                            (r.message && r.message.message)
                                                || __("No eligible claim lines found for export.")
                                        );
                                    }
                                },
                            });
                        }
                    );
                },
                __("Generate Claim Export"),
                __("Generate")
            );
        }, __("Claim Export"));

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
