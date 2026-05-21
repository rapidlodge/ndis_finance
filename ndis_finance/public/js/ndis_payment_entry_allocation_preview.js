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
