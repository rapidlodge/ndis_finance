frappe.ui.form.on("NDIS PE Production Activation Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS PE Production Activation Gate Item", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Activation Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Activation Exception Report", {
                activation_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Policy Readiness"), () => {
            frappe.set_route("query-report", "NDIS PE Production Activation Policy Readiness Report");
        }, __("Open"));

        if (frm.doc.source_adapter_run) {
            frm.add_custom_button(__("Open Adapter Run"), () => {
                frappe.set_route("Form", "NDIS PE Production Adapter Run", frm.doc.source_adapter_run);
            }, __("Evidence"));
        }

        if (frm.doc.source_preview) {
            frm.add_custom_button(__("Open Posting Preview"), () => {
                frappe.set_route("Form", "NDIS PE Production Posting Preview", frm.doc.source_preview);
            }, __("Evidence"));
        }

        if (frm.doc.mapping_gate) {
            frm.add_custom_button(__("Open Mapping Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Account Mapping Gate", frm.doc.mapping_gate);
            }, __("Evidence"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Activation Gate"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_production_activation_gate.cancel_pe_production_activation_gate",
                        args: {
                            activation_gate: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling production PE activation gate..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Activation Gate"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
