frappe.ui.form.on("NDIS Invoice Backed PE Smoke Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Smoke Lines"), () => {
            frappe.set_route("List", "NDIS Invoice Backed PE Smoke Line", {
                smoke_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Open"));
        }

        if (frm.doc.remittance_import) {
            frm.add_custom_button(__("Open Remittance Import"), () => {
                frappe.set_route("Form", "NDIS Remittance Import", frm.doc.remittance_import);
            }, __("Open"));
        }

        if (frm.doc.allocation_preview) {
            frm.add_custom_button(__("Open Allocation Preview"), () => {
                frappe.set_route("Form", "NDIS Payment Entry Allocation Preview", frm.doc.allocation_preview);
            }, __("Open"));
        }

        if (frm.doc.sandbox_payment_entry_run) {
            frm.add_custom_button(__("Open Sandbox PE Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Payment Entry Run", frm.doc.sandbox_payment_entry_run);
            }, __("Open"));
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__("Open Draft Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS Invoice Backed PE Smoke Run Report");
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
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
                        method: "ndis_finance.services.invoice_backed_pe_smoke.cancel_invoice_backed_pe_smoke",
                        args: {
                            smoke_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling invoice-backed PE smoke run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Smoke Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
