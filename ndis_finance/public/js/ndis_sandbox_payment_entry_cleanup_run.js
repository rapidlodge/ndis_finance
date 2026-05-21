frappe.ui.form.on("NDIS Sandbox Payment Entry Cleanup Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Cleanup Lines"), () => {
            frappe.set_route("List", "NDIS Sandbox Payment Entry Cleanup Line", {
                cleanup_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.target_sandbox_run) {
            frm.add_custom_button(__("Open Target Sandbox Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Payment Entry Run", frm.doc.target_sandbox_run);
            }, __("Open"));
        }

        if (frm.doc.target_payment_entry) {
            frm.add_custom_button(__("Open Target Payment Entry"), () => {
                frappe.set_route("Form", "Payment Entry", frm.doc.target_payment_entry);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Cleanup Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Payment Entry Cleanup Report");
        }, __("Open"));

        frm.add_custom_button(__("Open PE Hygiene Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Payment Entry Hygiene Report");
        }, __("Open"));

        if (!["Cancelled", "Cleaned"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Cancel Cleanup Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.sandbox_payment_entry_cleanup.cancel_sandbox_payment_entry_cleanup",
                        args: {
                            cleanup_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling cleanup run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Cleanup Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
