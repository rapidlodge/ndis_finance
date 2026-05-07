frappe.ui.form.on("NDIS Recovery Case", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Open Activities"), () => {
            frappe.set_route("List", "NDIS Recovery Activity", {
                recovery_case: frm.doc.name,
            });
        }, __("Open"));

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

        if (frm.doc.payment_reconciliation_batch) {
            frm.add_custom_button(__("Open Reconciliation Batch"), () => {
                frappe.set_route(
                    "Form",
                    "NDIS Payment Reconciliation Batch",
                    frm.doc.payment_reconciliation_batch
                );
            }, __("Open"));
        }

        if (!["Resolved", "Written Off", "Closed"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Add Follow-Up Activity"), () => {
                prompt_activity(frm);
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Escalate"), () => {
                prompt_escalate(frm);
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Resolve"), () => {
                prompt_resolve(frm);
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Write Off Control"), () => {
                prompt_write_off(frm);
            }, __("NDIS Actions"));
        }

        if (frm.doc.status !== "Closed") {
            frm.add_custom_button(__("Close Case"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "resolution_note",
                            label: __("Closing Note"),
                            fieldtype: "Small Text",
                            reqd: 1,
                        },
                    ],
                    (values) => {
                        frappe.call({
                            method: "ndis_finance.services.recovery_engine.close_recovery_case",
                            args: {
                                recovery_case: frm.doc.name,
                                resolution_note: values.resolution_note,
                            },
                            freeze: true,
                            freeze_message: __("Closing recovery case..."),
                            callback() {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Recovery case closed"),
                                    indicator: "green",
                                });
                            },
                        });
                    },
                    __("Close Recovery Case"),
                    __("Close")
                );
            }, __("NDIS Actions"));
        }
    },
});

function prompt_activity(frm) {
    frappe.prompt(
        [
            {
                fieldname: "activity_type",
                label: __("Activity Type"),
                fieldtype: "Select",
                options:
                    "\nCall\nEmail\nSMS\nNote\nRemittance Requested\nInvoice Resent\nEscalation\nPayment Received\nWrite Off Review\nResolved\nOther",
                default: "Note",
                reqd: 1,
            },
            {
                fieldname: "outcome",
                label: __("Outcome"),
                fieldtype: "Select",
                options:
                    "\nNo Answer\nLeft Message\nSpoke to Contact\nAwaiting Response\nPromised Payment\nRemittance Requested\nInvoice Resent\nEscalated\nResolved\nWrite Off Requested\nWrite Off Approved\nOther",
            },
            {
                fieldname: "next_follow_up_date",
                label: __("Next Follow Up Date"),
                fieldtype: "Date",
            },
            {
                fieldname: "activity_note",
                label: __("Activity Note"),
                fieldtype: "Small Text",
                reqd: 1,
            },
        ],
        (values) => {
            frappe.call({
                method: "ndis_finance.services.recovery_engine.add_recovery_activity",
                args: {
                    recovery_case: frm.doc.name,
                    activity_type: values.activity_type,
                    outcome: values.outcome,
                    next_follow_up_date: values.next_follow_up_date,
                    activity_note: values.activity_note,
                },
                freeze: true,
                freeze_message: __("Adding recovery activity..."),
                callback() {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Recovery activity added"),
                        indicator: "green",
                    });
                },
            });
        },
        __("Add Recovery Activity"),
        __("Add")
    );
}

function prompt_escalate(frm) {
    frappe.prompt(
        [
            {
                fieldname: "reason",
                label: __("Escalation Reason"),
                fieldtype: "Small Text",
                reqd: 1,
            },
            {
                fieldname: "next_follow_up_date",
                label: __("Next Follow Up Date"),
                fieldtype: "Date",
                default: frappe.datetime.add_days(frappe.datetime.now_date(), 2),
            },
        ],
        (values) => {
            frappe.call({
                method: "ndis_finance.services.recovery_engine.escalate_recovery_case",
                args: {
                    recovery_case: frm.doc.name,
                    reason: values.reason,
                    next_follow_up_date: values.next_follow_up_date,
                },
                freeze: true,
                freeze_message: __("Escalating recovery case..."),
                callback() {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Recovery case escalated"),
                        indicator: "orange",
                    });
                },
            });
        },
        __("Escalate Recovery Case"),
        __("Escalate")
    );
}

function prompt_resolve(frm) {
    frappe.prompt(
        [
            {
                fieldname: "recovered_amount",
                label: __("Recovered Amount"),
                fieldtype: "Currency",
                default: frm.doc.outstanding_amount || 0,
            },
            {
                fieldname: "resolution_note",
                label: __("Resolution Note"),
                fieldtype: "Small Text",
                reqd: 1,
            },
        ],
        (values) => {
            frappe.call({
                method: "ndis_finance.services.recovery_engine.resolve_recovery_case",
                args: {
                    recovery_case: frm.doc.name,
                    recovered_amount: values.recovered_amount,
                    resolution_note: values.resolution_note,
                },
                freeze: true,
                freeze_message: __("Resolving recovery case..."),
                callback() {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Recovery case resolved"),
                        indicator: "green",
                    });
                },
            });
        },
        __("Resolve Recovery Case"),
        __("Resolve")
    );
}

function prompt_write_off(frm) {
    frappe.prompt(
        [
            {
                fieldname: "written_off_amount",
                label: __("Written Off Amount"),
                fieldtype: "Currency",
                default: frm.doc.outstanding_amount || 0,
                reqd: 1,
            },
            {
                fieldname: "resolution_note",
                label: __("Write-Off Control Note"),
                fieldtype: "Small Text",
                reqd: 1,
            },
        ],
        (values) => {
            frappe.confirm(
                __(
                    "This only updates NDIS recovery control status. It does not create Journal Entry or GL write-off. Continue?"
                ),
                () => {
                    frappe.call({
                        method: "ndis_finance.services.recovery_engine.write_off_recovery_case",
                        args: {
                            recovery_case: frm.doc.name,
                            written_off_amount: values.written_off_amount,
                            resolution_note: values.resolution_note,
                        },
                        freeze: true,
                        freeze_message: __("Marking recovery case as written off..."),
                        callback() {
                            frm.reload_doc();
                            frappe.show_alert({
                                message: __(
                                    "Recovery case marked as written off for control purposes"
                                ),
                                indicator: "gray",
                            });
                        },
                    });
                }
            );
        },
        __("Write Off Control"),
        __("Write Off")
    );
}
