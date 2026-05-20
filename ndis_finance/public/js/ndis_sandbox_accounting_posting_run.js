frappe.ui.form.on("NDIS Sandbox Accounting Posting Run", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Run Lines"), () => {
            frappe.set_route("List", "NDIS Sandbox Accounting Posting Run Line", {
                sandbox_run: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.posting_request) {
            frm.add_custom_button(__("Open Posting Request"), () => {
                frappe.set_route("Form", "NDIS Accounting Posting Request", frm.doc.posting_request);
            }, __("Open"));
        }

        if (frm.doc.journal_entry) {
            frm.add_custom_button(__("Open Draft Journal Entry"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("Open"));
        }

        frm.add_custom_button(__("Open Run Report"), () => {
            frappe.set_route("query-report", "NDIS Sandbox Accounting Posting Run Report");
        }, __("Open"));

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Sandbox Run"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.sandbox_accounting_posting.cancel_sandbox_accounting_posting_run",
                        args: {
                            sandbox_run: frm.doc.name,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Cancelling sandbox run..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Sandbox Run"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
