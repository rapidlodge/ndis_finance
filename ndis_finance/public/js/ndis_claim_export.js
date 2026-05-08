frappe.ui.form.on("NDIS Claim Export", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Open Export Lines"), () => {
            frappe.set_route("List", "NDIS Claim Export Line", {
                claim_export: frm.doc.name,
            });
        }, __("Open"));

        if (frm.doc.claim_batch) {
            frm.add_custom_button(__("Open Claim Batch"), () => {
                frappe.set_route("Form", "NDIS Claim Batch", frm.doc.claim_batch);
            }, __("Open"));
        }

        if (frm.doc.export_mapping_template) {
            frm.add_custom_button(__("Open Mapping Template"), () => {
                frappe.set_route(
                    "Form",
                    "NDIS Claim Export Mapping Template",
                    frm.doc.export_mapping_template
                );
            }, __("Open"));
        }

        if (frm.doc.export_file) {
            frm.add_custom_button(__("Download Export File"), () => {
                window.open(frm.doc.export_file);
            }, __("Open"));
        }

        if (frm.doc.status === "Generated") {
            frm.add_custom_button(__("Cancel Export Control"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "reason",
                            label: __("Cancellation Reason"),
                            fieldtype: "Small Text",
                            reqd: 1,
                        },
                    ],
                    (values) => {
                        frappe.confirm(
                            __("This only cancels the internal export control record. It does not reverse any external submission or accounting entry. Continue?"),
                            () => {
                                frappe.call({
                                    method: "ndis_finance.services.claim_exporter.cancel_claim_export",
                                    args: {
                                        claim_export: frm.doc.name,
                                        reason: values.reason,
                                    },
                                    freeze: true,
                                    freeze_message: __("Cancelling claim export..."),
                                    callback() {
                                        frm.reload_doc();
                                        frappe.show_alert({
                                            message: __("Claim export cancelled for control purposes only"),
                                            indicator: "gray",
                                        });
                                    },
                                });
                            }
                        );
                    },
                    __("Cancel Claim Export"),
                    __("Cancel Export")
                );
            }, __("NDIS Actions"));
        }
    },
});
