frappe.ui.form.on("NDIS PE Smoke Invoice Source Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Run Items"), () => {
            frappe.set_route("List", "NDIS PE Smoke Invoice Source Run Item", {
                source_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS PE Smoke Invoice Source Run Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Smoke Invoice Source Exception Report", {
                source_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Source Hygiene"), () => {
            frappe.set_route("query-report", "NDIS PE Smoke Invoice Source Hygiene Report");
        }, __("Open"));

        if (frm.doc.source_sales_invoice) {
            frm.add_custom_button(__("Open Source Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.source_sales_invoice);
            }, __("Evidence"));
        }

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Activation Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.submitted_smoke_gate) {
            frm.add_custom_button(__("Open Submitted Smoke Gate"), () => {
                frappe.set_route("Form", "NDIS PE Submitted Smoke Gate", frm.doc.submitted_smoke_gate);
            }, __("Evidence"));
        }

        if (frm.doc.status !== "Cancelled" && frm.doc.status !== "Source Cancelled") {
            frm.add_custom_button(__("Cancel Source Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_smoke_invoice_source_harness.cancel_pe_smoke_invoice_source_run",
                        args: {
                            source_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling source run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Source Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
