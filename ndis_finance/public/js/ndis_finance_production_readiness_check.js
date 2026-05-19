frappe.ui.form.on("NDIS Finance Production Readiness Check", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Check Items"), () => {
            frappe.set_route("List", "NDIS Finance Production Readiness Check Item", {
                readiness_check: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Readiness Report"), () => {
            frappe.set_route("query-report", "NDIS Finance Production Readiness Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Finance Readiness Exception Report", {
                readiness_check: frm.doc.name
            });
        }, __("Open"));

        if (!frm.doc.production_ready_allowed && frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Acknowledge Readiness"), () => {
                frappe.prompt([
                    {
                        fieldname: "acknowledgement",
                        label: __("Acknowledgement"),
                        fieldtype: "Data",
                        reqd: 1,
                        description: __("Required: ") + (frm.doc.required_ack || "")
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.production_readiness.acknowledge_production_readiness",
                        args: {
                            readiness_check: frm.doc.name,
                            acknowledgement: values.acknowledgement
                        },
                        freeze: true,
                        freeze_message: __("Acknowledging readiness..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Acknowledge Readiness"), __("Acknowledge"));
            }, __("NDIS Actions"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Check"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.production_readiness.cancel_production_readiness_check",
                        args: {
                            readiness_check: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling readiness check..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Readiness Check"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
