frappe.ui.form.on("NDIS PE Production Adapter Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Adapter Lines"), () => {
            frappe.set_route("List", "NDIS PE Production Adapter Run Line", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Adapter Run Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Line Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Adapter Run Line Report", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Adapter Exception Report", {
                adapter_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.source_preview) {
            frm.add_custom_button(__("Open Source Preview"), () => {
                frappe.set_route("Form", "NDIS PE Production Posting Preview", frm.doc.source_preview);
            }, __("Open"));
        }

        if (frm.doc.mapping_gate) {
            frm.add_custom_button(__("Open Mapping Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Account Mapping Gate", frm.doc.mapping_gate);
            }, __("Open"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Adapter Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_production_adapter_hard_block.cancel_pe_production_adapter_run",
                        args: {
                            adapter_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling production PE adapter run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Adapter Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
