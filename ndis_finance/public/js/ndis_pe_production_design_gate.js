frappe.ui.form.on("NDIS PE Production Design Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS PE Production Design Gate Item", {
                design_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Design Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS PE Production Design Exception Report", {
                design_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Policy Register"), () => {
            frappe.set_route("query-report", "NDIS PE Production Policy Register");
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Gate"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_production_design_gate.cancel_pe_production_design_gate",
                        args: {
                            design_gate: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling production PE design gate..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Design Gate"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
