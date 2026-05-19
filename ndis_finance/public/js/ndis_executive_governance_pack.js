frappe.ui.form.on("NDIS Executive Governance Pack", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Items"), () => {
            frappe.set_route("List", "NDIS Executive Governance Pack Item", {
                governance_pack: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.source_snapshot) {
            frm.add_custom_button(__("Open Snapshot"), () => {
                frappe.set_route("Form", "NDIS Executive Dashboard Snapshot", frm.doc.source_snapshot);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Pack Report"), () => {
            frappe.set_route("query-report", "NDIS Executive Governance Pack Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Detail Report"), () => {
            frappe.set_route("query-report", "NDIS Governance Pack Detail Report", {
                governance_pack: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.board_pack_html_file) {
            frm.add_custom_button(__("Open HTML Export"), () => {
                window.open(frm.doc.board_pack_html_file);
            }, __("Export"));
        }

        if (frm.doc.board_pack_csv_file) {
            frm.add_custom_button(__("Open CSV Export"), () => {
                window.open(frm.doc.board_pack_csv_file);
            }, __("Export"));
        }

        if (frm.doc.status === "Generated") {
            frm.add_custom_button(__("Sign Off Pack"), () => {
                frappe.prompt([
                    {
                        fieldname: "signoff_note",
                        label: __("Sign-off Note"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.confirm(
                        __("This signs off the governance pack internally only. No email, accounting, payroll, STP, ABA, or payment movement will be created. Continue?"),
                        () => {
                            frappe.call({
                                method: "ndis_finance.services.executive_governance_pack.signoff_governance_pack",
                                args: {
                                    governance_pack: frm.doc.name,
                                    signoff_note: values.signoff_note
                                },
                                freeze: true,
                                freeze_message: __("Signing off governance pack..."),
                                callback() {
                                    frm.reload_doc();
                                }
                            });
                        }
                    );
                }, __("Sign Off Pack"), __("Sign Off"));
            }, __("NDIS Actions"));
        }

        if (!["Cancelled", "Signed Off"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Cancel Pack"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_governance_pack.cancel_governance_pack",
                        args: {
                            governance_pack: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling governance pack..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Governance Pack"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
