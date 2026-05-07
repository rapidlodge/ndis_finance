frappe.ui.form.on("NDIS Recovery Email Draft", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        if (frm.doc.recovery_case) {
            frm.add_custom_button(__("Open Recovery Case"), () => {
                frappe.set_route("Form", "NDIS Recovery Case", frm.doc.recovery_case);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }

        if (frm.doc.claim_line) {
            frm.add_custom_button(__("Open Claim Line"), () => {
                frappe.set_route("Form", "NDIS Claim Line", frm.doc.claim_line);
            }, __("Open"));
        }

        if (frm.doc.funding_leakage) {
            frm.add_custom_button(__("Open Funding Leakage"), () => {
                frappe.set_route("Form", "NDIS Funding Leakage Register", frm.doc.funding_leakage);
            }, __("Open"));
        }

        if (frm.doc.activity) {
            frm.add_custom_button(__("Open Activity"), () => {
                frappe.set_route("Form", "NDIS Recovery Activity", frm.doc.activity);
            }, __("Open"));
        }

        if (frm.doc.status === "Draft") {
            frm.add_custom_button(__("Approve Draft"), () => {
                frappe.call({
                    method: "ndis_finance.services.recovery_communication.approve_email_draft",
                    args: {
                        email_draft: frm.doc.name,
                    },
                    freeze: true,
                    freeze_message: __("Approving draft..."),
                    callback() {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("Email draft approved. No email was sent automatically."),
                            indicator: "green",
                        });
                    },
                });
            }, __("NDIS Actions"));
        }

        if (["Draft", "Approved"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Mark Sent Manually"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "note",
                            label: __("Manual Send Note"),
                            fieldtype: "Small Text",
                            default: "Email was sent manually by finance user outside the system.",
                        },
                    ],
                    (values) => {
                        frappe.call({
                            method: "ndis_finance.services.recovery_communication.mark_email_draft_sent_manually",
                            args: {
                                email_draft: frm.doc.name,
                                note: values.note,
                            },
                            freeze: true,
                            freeze_message: __("Marking draft as sent manually..."),
                            callback() {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __(
                                        "Marked sent manually. No email was sent by the system."
                                    ),
                                    indicator: "green",
                                });
                            },
                        });
                    },
                    __("Mark Sent Manually"),
                    __("Confirm")
                );
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Cancel Draft"), () => {
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
                        frappe.call({
                            method: "ndis_finance.services.recovery_communication.cancel_email_draft",
                            args: {
                                email_draft: frm.doc.name,
                                reason: values.reason,
                            },
                            freeze: true,
                            freeze_message: __("Cancelling draft..."),
                            callback() {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Email draft cancelled"),
                                    indicator: "gray",
                                });
                            },
                        });
                    },
                    __("Cancel Email Draft"),
                    __("Cancel Draft")
                );
            }, __("NDIS Actions"));
        }
    },
});
