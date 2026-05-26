frappe.ui.form.on("NDIS PE Production Posting Preview", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Preview Lines"), () => {
            frappe.set_route("List", "NDIS PE Production Posting Preview Line", {
                posting_preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Preview Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Posting Preview Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Line Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Posting Preview Line Report", {
                posting_preview: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Posting Preview Exception Report", {
                posting_preview: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.mapping_gate) {
            frm.add_custom_button(__("Open Mapping Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Account Mapping Gate", frm.doc.mapping_gate);
            }, __("Open"));
        }

        if (frm.doc.design_gate) {
            frm.add_custom_button(__("Open Design Gate"), () => {
                frappe.set_route("Form", "NDIS PE Production Design Gate", frm.doc.design_gate);
            }, __("Open"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Preview"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_production_posting_preview.cancel_pe_production_posting_preview",
                        args: {
                            posting_preview: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling production PE posting preview..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Posting Preview"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
