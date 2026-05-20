frappe.ui.form.on("NDIS Sandbox Accounting Cleanup Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Cleanup Lines"), () => {
            frappe.set_route("List", "NDIS Sandbox Accounting Cleanup Line", {
                cleanup_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.target_sandbox_run) {
            frm.add_custom_button(__("Open Target Sandbox Run"), () => {
                frappe.set_route("Form", "NDIS Sandbox Accounting Posting Run", frm.doc.target_sandbox_run);
            }, __("Open"));
        }

        if (frm.doc.target_journal_entry) {
            frm.add_custom_button(__("Open Target Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.target_journal_entry);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Cleanup Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Accounting Cleanup Report");
        }, __("Open"));

        frm.add_custom_button(__("Open JE Hygiene Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Journal Entry Hygiene Report");
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
                        method: "ndis_finance.services.sandbox_accounting_cleanup.cancel_sandbox_accounting_cleanup",
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
