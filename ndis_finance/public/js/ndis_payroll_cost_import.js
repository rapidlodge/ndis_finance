frappe.ui.form.on("NDIS Payroll Cost Import", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Import Lines"), () => {
            frappe.set_route("List", "NDIS Payroll Cost Import Line", {
                payroll_cost_import: frm.doc.name,
            });
        }, __("Open"));

        if (frm.doc.au_payroll_run_log) {
            frm.add_custom_button(__("Open AU Payroll Run"), () => {
                frappe.set_route("Form", "AU Payroll Run Log", frm.doc.au_payroll_run_log);
            }, __("Open"));
        }

        frm.add_custom_button(__("Refresh Summary"), () => {
            frappe.call({
                method: "ndis_finance.services.payroll_cost_bridge.refresh_payroll_cost_import_summary",
                args: {
                    payroll_cost_import: frm.doc.name,
                },
                freeze: true,
                freeze_message: __("Refreshing payroll cost import summary..."),
                callback() {
                    frm.reload_doc();
                },
            });
        }, __("NDIS Actions"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Payroll Cost Import"), () => {
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
                            __("This cancels the NDIS payroll cost import and related management cost pools only. It does not reverse payroll, STP, ABA, GL, Journal Entry, or Payment Entry. Continue?"),
                            () => {
                                frappe.call({
                                    method: "ndis_finance.services.payroll_cost_bridge.cancel_payroll_cost_import",
                                    args: {
                                        payroll_cost_import: frm.doc.name,
                                        reason: values.reason,
                                    },
                                    freeze: true,
                                    freeze_message: __("Cancelling payroll cost import..."),
                                    callback() {
                                        frm.reload_doc();
                                        frappe.show_alert({
                                            message: __("Payroll cost import cancelled for management costing only."),
                                            indicator: "gray",
                                        });
                                    },
                                });
                            }
                        );
                    },
                    __("Cancel Payroll Cost Import"),
                    __("Cancel")
                );
            }, __("NDIS Actions"));
        }
    },
});
