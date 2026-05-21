frappe.ui.form.on("NDIS Sandbox Payment Entry Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Run Lines"), () => {
            frappe.set_route("List", "NDIS Sandbox Payment Entry Run Line", {
                sandbox_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.allocation_preview) {
            frm.add_custom_button(__("Open Allocation Preview"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Allocation Preview", frm.doc.allocation_preview);
            }, __("Open"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Draft Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Open"));
        }

        if (frm.doc.mapping_rule) {
            frm.add_custom_button(__("Open Mapping Rule"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Mapping Rule", frm.doc.mapping_rule);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Payment Entry Run Report");
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Sandbox PE Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.sandbox_payment_entry_posting.cancel_sandbox_payment_entry_run",
                        args: {
                            sandbox_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling sandbox Payment Entry run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Sandbox Payment Entry Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
