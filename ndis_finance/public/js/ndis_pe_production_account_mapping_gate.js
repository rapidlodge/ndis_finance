frappe.ui.form.on("NDIS PE Production Account Mapping Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS PE Production Account Mapping Gate Item", {
                mapping_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Account Mapping Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Account Mapping Exception Report", {
                mapping_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Mapping Control Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Mapping Control Report");
        }, __("Open"));

        if (frm.doc.allowed_bank_account) {
            frm.add_custom_button(__("Open Bank Account"), () => {
                frappe.set_route("Form", "Account", frm.doc.allowed_bank_account);
            }, __("Open"));
        }

        if (frm.doc.allowed_receivable_account) {
            frm.add_custom_button(__("Open Receivable Account"), () => {
                frappe.set_route("Form", "Account", frm.doc.allowed_receivable_account);
            }, __("Open"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Gate"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_production_account_mapping.cancel_pe_production_account_mapping_gate",
                        args: {
                            mapping_gate: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling production PE account mapping gate..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Mapping Gate"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
