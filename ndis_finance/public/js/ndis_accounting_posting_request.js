frappe.ui.form.on("NDIS Accounting Posting Request", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Request Lines"), () => {
            frappe.set_route("List", "NDIS Accounting Posting Request Line", {
                posting_request: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.posting_preview) {
            frm.add_custom_button(__("Open Posting Preview"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Preview", frm.doc.posting_preview);
            }, __("Open"));
        }

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

        frm.add_custom_button(__("Open Request Register"), () => {
            frappe.set_route("query-report", "NDIS Accounting Posting Request Register Report");
        }, __("Open"));

        if (frm.doc.status === "Pending Approval") {
            frm.add_custom_button(__("Approve for Dry-run"), () => {
                frappe.prompt([
                    {
                        fieldname: "approval_note",
                        label: __("Approval Note"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.confirm(
                        __("This approval is for dry-run simulation only. It will not enable real accounting posting. Continue?"),
                        () => {
                            frappe.call({
                                method: "ndis_finance.services.accounting_posting_requests.approve_accounting_posting_request",
                                args: {
                                    posting_request: frm.doc.name,
                                    approval_note: values.approval_note
                                },
                                freeze: true,
                                freeze_message: __("Approving posting request..."),
                                callback() {
                                    frm.reload_doc();
                                }
                            });
                        }
                    );
                }, __("Approve for Dry-run"), __("Approve"));
            }, __("NDIS Actions"));
        }

        if (["Pending Approval", "Approved"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Reject Request"), () => {
                frappe.prompt([
                    {
                        fieldname: "rejection_reason",
                        label: __("Rejection Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.accounting_posting_requests.reject_accounting_posting_request",
                        args: {
                            posting_request: frm.doc.name,
                            rejection_reason: values.rejection_reason
                        },
                        freeze: true,
                        freeze_message: __("Rejecting posting request..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Reject Request"), __("Reject"));
            }, __("NDIS Actions"));
        }

        if (["Approved", "Dry Run Failed", "Dry Run Passed"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Run Dry-run Simulation"), () => {
                frappe.call({
                    method: "ndis_finance.services.accounting_posting_requests.dry_run_accounting_posting_request",
                    args: {
                        posting_request: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Running dry-run simulation..."),
                    callback(r) {
                        frm.reload_doc();
                        frappe.msgprint({
                            title: __("Dry-run Result"),
                            message: `<pre>${JSON.stringify(r.message || {}, null, 2)}</pre>`,
                            indicator: "blue"
                        });
                    }
                });
            }, __("NDIS Actions"));
        }

        if (!["Cancelled", "Rejected"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Cancel Request"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.accounting_posting_requests.cancel_accounting_posting_request",
                        args: {
                            posting_request: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling posting request..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Posting Request"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
