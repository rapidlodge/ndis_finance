frappe.ui.form.on("NDIS Executive Exception Alert", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (frm.doc.rule) {
            frm.add_custom_button(__("Open Rule"), () => {
                frappe.set_route("Form", "NDIS Executive Exception Rule", frm.doc.rule);
            }, __("Open"));
        }

        if (frm.doc.snapshot) {
            frm.add_custom_button(__("Open Snapshot"), () => {
                frappe.set_route("Form", "NDIS Executive Dashboard Snapshot", frm.doc.snapshot);
            }, __("Open"));
        }

        if (frm.doc.status === "Open") {
            frm.add_custom_button(__("Mark In Review"), () => {
                frappe.prompt([
                    {
                        fieldname: "note",
                        label: __("Review Note"),
                        fieldtype: "Small Text"
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_exceptions.mark_exception_alert_in_review",
                        args: {
                            alert: frm.doc.name,
                            note: values.note
                        },
                        freeze: true,
                        freeze_message: __("Marking alert in review..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Mark In Review"), __("Confirm"));
            }, __("NDIS Actions"));
        }

        if (["Open", "In Review"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Resolve Alert"), () => {
                frappe.prompt([
                    {
                        fieldname: "resolution_note",
                        label: __("Resolution Note"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_exceptions.resolve_exception_alert",
                        args: {
                            alert: frm.doc.name,
                            resolution_note: values.resolution_note
                        },
                        freeze: true,
                        freeze_message: __("Resolving alert..."),
                        callback() {
                            frm.reload_doc();
                            frappe.show_alert({
                                message: __("Exception alert resolved only."),
                                indicator: "green"
                            });
                        }
                    });
                }, __("Resolve Alert"), __("Resolve"));
            }, __("NDIS Actions"));

            frm.add_custom_button(__("Cancel Alert"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.executive_exceptions.cancel_exception_alert",
                        args: {
                            alert: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling alert..."),
                        callback() {
                            frm.reload_doc();
                            frappe.show_alert({
                                message: __("Exception alert cancelled only."),
                                indicator: "gray"
                            });
                        }
                    });
                }, __("Cancel Alert"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
