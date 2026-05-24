frappe.ui.form.on("NDIS Sandbox Invoice Test Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Test Lines"), () => {
            frappe.set_route("List", "NDIS Sandbox Invoice Test Line", {
                test_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.customer) {
            frm.add_custom_button(__("Open Customer"), () => {
                frappe.set_route("Form", "Customer", frm.doc.customer);
            }, __("Open"));
        }

        if (frm.doc.item) {
            frm.add_custom_button(__("Open Item"), () => {
                frappe.set_route("Form", "Item", frm.doc.item);
            }, __("Open"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Invoice Test Run Report");
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Test Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.sandbox_invoice_test_harness.cancel_sandbox_invoice_test_run",
                        args: {
                            test_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling sandbox invoice test run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Test Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
