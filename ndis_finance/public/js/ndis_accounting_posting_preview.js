frappe.ui.form.on("NDIS Accounting Posting Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Accounting Posting Preview Line", {
                posting_preview: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.policy) {
            frm.add_custom_button(__("Open Policy"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Policy", frm.doc.policy);
            }, __("Open"));
        }

        if (frm.doc.source_doctype && frm.doc.source_name) {
            frm.add_custom_button(__("Open Source"), () => {
                frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
            }, __("Open"));
        }

        if (frm.doc.readiness_check) {
            frm.add_custom_button(__("Open Readiness Check"), () => {
                frappe.set_route("Form", "NDIS Finance Production Readiness Check", frm.doc.readiness_check);
            }, __("Open"));
        }

        if (frm.doc.governance_pack) {
            frm.add_custom_button(__("Open Governance Pack"), () => {
                frappe.set_route("Form", "NDIS Executive Governance Pack", frm.doc.governance_pack);
            }, __("Open"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Create Posting Request"), () => {
                frappe.confirm(
                    __("This creates an internal posting request for approval and dry-run only. It will not create any accounting entry. Continue?"),
                    () => {
                        frappe.call({
                            method: "ndis_finance.services.accounting_posting_requests.create_accounting_posting_request_from_preview",
                            args: {
                                posting_preview: frm.doc.name,
                                replace_existing: 0
                            },
                            freeze: true,
                            freeze_message: __("Creating posting request..."),
                            callback(r) {
                                if (r.message && r.message.posting_request) {
                                    frappe.set_route("Form", "NDIS Accounting Posting Request", r.message.posting_request);
                                } else {
                                    frappe.msgprint((r.message && r.message.message) || __("Posting request was not created."));
                                }
                            }
                        });
                    }
                );
            }, __("NDIS Actions"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Preview"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.accounting_posting_blueprint.cancel_accounting_posting_preview",
                        args: {
                            posting_preview: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling posting preview..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Posting Preview"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
