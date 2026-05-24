frappe.ui.form.on("NDIS Sandbox Accounting Cleanup Pack", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Cleanup Lines"), () => {
            frappe.set_route("List", "NDIS Sandbox Accounting Cleanup Pack Line", {
                cleanup_pack: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.target_payment_entry) {
            frm.add_custom_button(__("Open Target Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.target_payment_entry);
            }, __("Open"));
        }

        if (frm.doc.target_sales_invoice) {
            frm.add_custom_button(__("Open Target Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.target_sales_invoice);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Cleanup Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Accounting Cleanup Pack Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Hygiene Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Accounting Hygiene Report");
        }, __("Open"));

        if (!["Cancelled", "Cleaned"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Cancel Cleanup Pack"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.sandbox_accounting_cleanup_pack.cancel_sandbox_accounting_cleanup_pack",
                        args: {
                            cleanup_pack: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling sandbox accounting cleanup pack..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Cleanup Pack"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
