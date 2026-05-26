frappe.ui.form.on("NDIS PE Single Record Draft Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Run Items"), () => {
            frappe.set_route("List", "NDIS PE Single Record Draft Smoke Run Item", {
                smoke_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS PE Single Record Draft Smoke Run Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Single Record Draft Smoke Exception Report", {
                smoke_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open PE Hygiene Report"), () => {
            frappe.set_route("query-report", "NDIS PE Draft Smoke Payment Entry Hygiene Report");
        }, __("Open"));

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Activation Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Evidence"));
        }

        if (frm.doc.draft_payment_entry) {
            frm.add_custom_button(__("Open Draft Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.draft_payment_entry);
            }, __("Evidence"));
        }

        if (frm.doc.cleanup_required && frm.doc.draft_payment_entry) {
            frm.add_custom_button(__("Cleanup Draft PE"), () => {
                frappe.prompt([
                    {
                        fieldname: "acknowledgement",
                        label: __("Acknowledgement"),
                        fieldtype: "Data",
                        reqd: 1,
                        description: __("Type I_CONFIRM_DELETE_PHASE5F_DRAFT_PE_ONLY")
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_single_record_draft_smoke.cleanup_pe_single_record_draft_smoke",
                        args: {
                            smoke_run: frm.doc.name,
                            acknowledgement: values.acknowledgement
                        },
                        freeze: true,
                        freeze_message: __("Cleaning up draft Payment Entry..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cleanup Draft Payment Entry"), __("Cleanup"));
            }, __("NDIS Actions"));
        }

        if (frm.doc.status !== "Cancelled" && !frm.doc.cleanup_required) {
            frm.add_custom_button(__("Cancel Smoke Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_single_record_draft_smoke.cancel_pe_single_record_draft_smoke",
                        args: {
                            smoke_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling draft smoke run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Smoke Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
