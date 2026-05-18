frappe.ui.form.on("NDIS Cost Pool", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Allocation Entries"), () => {
            frappe.set_route("List", "NDIS Cost Allocation Entry", {
                cost_pool: frm.doc.name,
            });
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Allocate Cost Pool"), () => {
                frappe.confirm(
                    __("This creates NDIS management cost allocation entries only. It does not create GL, Journal Entry, Payment Entry, payroll posting, or accounting movement. Continue?"),
                    () => {
                        frappe.call({
                            method: "ndis_finance.services.cost_allocation.allocate_cost_pool",
                            args: {
                                cost_pool: frm.doc.name,
                                replace_existing: 1,
                            },
                            freeze: true,
                            freeze_message: __("Allocating cost pool..."),
                            callback() {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Cost pool allocated for management reporting only."),
                                    indicator: "green",
                                });
                            },
                        });
                    }
                );
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Refresh Summary"), () => {
                frappe.call({
                    method: "ndis_finance.services.cost_allocation.refresh_cost_pool_summary",
                    args: {
                        cost_pool: frm.doc.name,
                    },
                    freeze: true,
                    freeze_message: __("Refreshing summary..."),
                    callback() {
                        frm.reload_doc();
                    },
                });
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Cancel Cost Pool"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1,
                    },
                ], (values) => {
                    frappe.confirm(
                        __("This cancels the cost allocation control only. No accounting reversal will be created. Continue?"),
                        () => {
                            frappe.call({
                                method: "ndis_finance.services.cost_allocation.cancel_cost_pool",
                                args: {
                                    cost_pool: frm.doc.name,
                                    reason: values.reason,
                                },
                                freeze: true,
                                freeze_message: __("Cancelling cost pool..."),
                                callback() {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Cost pool cancelled for management reporting only."),
                                        indicator: "gray",
                                    });
                                },
                            });
                        }
                    );
                }, __("Cancel Cost Pool"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    },
});
