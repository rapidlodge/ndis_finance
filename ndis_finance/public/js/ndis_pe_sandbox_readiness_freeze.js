frappe.ui.form.on("NDIS PE Sandbox Readiness Freeze", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Freeze Items"), () => {
            frappe.set_route("List", "NDIS PE Sandbox Readiness Freeze Item", {
                readiness_freeze: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Freeze Report"), () => {
            frappe.set_route("query-report", "NDIS PE Sandbox Readiness Freeze Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Item Report"), () => {
            frappe.set_route("query-report", "NDIS PE Sandbox Readiness Freeze Item Report", {
                readiness_freeze: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Freeze"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.pe_sandbox_readiness_freeze.cancel_pe_sandbox_readiness_freeze",
                        args: {
                            readiness_freeze: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling readiness freeze..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Readiness Freeze"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
