frappe.ui.form.on("NDIS PE Submitted Smoke Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS PE Submitted Smoke Gate Item", {
                submitted_smoke_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS PE Submitted Smoke Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Submitted Smoke Exception Report", {
                submitted_smoke_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Source Readiness"), () => {
            frappe.set_route("query-report", "NDIS PE Submitted Smoke Source Readiness Report");
        }, __("Open"));

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Open Sales Invoice"), () => {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("Evidence"));
        }

        if (frm.doc.activation_gate) {
            frm.add_custom_button(__("Open Activation Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Activation Gate", frm.doc.activation_gate);
            }, __("Evidence"));
        }

        if (frm.doc.draft_smoke_run) {
            frm.add_custom_button(__("Open Draft Smoke Run"), () => {
                frappe.set_route("Form", "NDIS PE Single Record Draft Smoke Run", frm.doc.draft_smoke_run);
            }, __("Evidence"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Submitted Smoke Gate"), () => {
                frappe.prompt([{ fieldname: "reason", label: __("Cancellation Reason"), fieldtype: "Small Text", reqd: 1 }], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_submitted_smoke_gate.cancel_pe_submitted_smoke_gate",
                        args: { submitted_smoke_gate: frm.doc.name, reason: values.reason },
                        freeze: true,
                        freeze_message: __("Cancelling submitted PE smoke gate..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Submitted Smoke Gate"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
