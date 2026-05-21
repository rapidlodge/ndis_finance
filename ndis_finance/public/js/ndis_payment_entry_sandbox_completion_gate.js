frappe.ui.form.on("NDIS Payment Entry Sandbox Completion Gate", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Gate Items"), () => {
            frappe.set_route("List", "NDIS Payment Entry Sandbox Completion Gate Item", {
                completion_gate: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Gate Report"), () => {
            frappe.set_route("query-report", "NDIS Payment Entry Sandbox Completion Gate Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Payment Entry Sandbox Completion Exception Report", {
                completion_gate: frm.doc.name
            });
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
                        method: "ndis_finance.services.payment_entry_sandbox_completion.cancel_payment_entry_sandbox_completion_gate",
                        args: {
                            completion_gate: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling Payment Entry sandbox completion gate..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Gate"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
