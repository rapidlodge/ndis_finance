frappe.ui.form.on("NDIS Payment Entry Allocation Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS Payment Entry Allocation Preview Line", {
                allocation_preview: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.mapping_rule) {
            frm.add_custom_button(__("Open Mapping Rule"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Mapping Rule", frm.doc.mapping_rule);
            }, __("Open"));
        }

        if (frm.doc.remittance_import) {
            frm.add_custom_button(__("Open Remittance Import"), () => {
                frappe.set_route("Form", "NDIS Remittance Import", frm.doc.remittance_import);
            }, __("Open"));
        }

        if (frm.doc.design_review) {
            frm.add_custom_button(__("Open Design Review"), () => {
                frappe.set_route("Form", "NDIS Accounting Design Review", frm.doc.design_review);
            }, __("Open"));
        }

        if (frm.doc.sandbox_completion_gate) {
            frm.add_custom_button(__("Open Sandbox Completion Gate"), () => {
                frappe.set_route("Form", "NDIS Accounting Sandbox Completion Gate", frm.doc.sandbox_completion_gate);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Allocation Preview Report"), () => {
            frappe.set_route("query-report", "NDIS Payment Entry Allocation Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Payment Entry Allocation Exception Report", {
                allocation_preview: frm.doc.name
            });
        }, __("Open"));

        if (["Previewed", "Needs Review"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Create Sandbox Draft Payment Entry"), () => {
                frappe.prompt([
                    {
                        fieldname: "acknowledgement",
                        label: __("Acknowledgement"),
                        fieldtype: "Data",
                        reqd: 1,
                        description: __("Required: I_CONFIRM_NDIS_FINANCE_SANDBOX_PAYMENT_ENTRY_DRAFT_ONLY")
                    },
                    {
                        fieldname: "bank_account",
                        label: __("Fallback Bank Account / Paid To"),
                        fieldtype: "Link",
                        options: "Account"
                    },
                    {
                        fieldname: "receivable_account",
                        label: __("Fallback Receivable Account / Paid From"),
                        fieldtype: "Link",
                        options: "Account"
                    },
                    {
                        fieldname: "fallback_customer",
                        label: __("Fallback Customer"),
                        fieldtype: "Link",
                        options: "Customer"
                    }
                ], (values) => {
                    frappe.confirm(
                        __("This creates a sandbox draft Payment Entry only. It will not submit, will not create GL, and is blocked from submission. Continue?"),
                        () => {
                            frappe.call({
                                method: "ndis_finance.services.sandbox_payment_entry_posting.create_sandbox_payment_entry_draft",
                                args: {
                                    allocation_preview: frm.doc.name,
                                    acknowledgement: values.acknowledgement,
                                    bank_account: values.bank_account,
                                    receivable_account: values.receivable_account,
                                    fallback_customer: values.fallback_customer
                                },
                                freeze: true,
                                freeze_message: __("Creating sandbox draft Payment Entry..."),
                                callback(r) {
                                    if (r.message && r.message.sandbox_run) {
                                        frappe.set_route("Form", "NDIS Sandbox Payment Entry Run", r.message.sandbox_run);
                                    } else {
                                        frappe.msgprint({
                                            title: __("Sandbox Payment Entry Result"),
                                            message: `<pre>${JSON.stringify(r.message || {}, null, 2)}</pre>`,
                                            indicator: "blue"
                                        });
                                    }
                                }
                            });
                        }
                    );
                }, __("Create Sandbox Draft Payment Entry"), __("Create"));
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
                        method: "ndis_finance.services.payment_entry_sandbox_design.cancel_payment_entry_allocation_preview",
                        args: {
                            allocation_preview: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling allocation preview..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Allocation Preview"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
