frappe.ui.form.on("NDIS Accounting Design Review", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Review Items"), () => {
            frappe.set_route("List", "NDIS Accounting Design Review Item", { design_review: frm.doc.name });
        }, __("Open"));

        frm.add_custom_button(__("Open Review Report"), () => {
            frappe.set_route("query-report", "NDIS Accounting Design Review Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Accounting Design Exception Report", { design_review: frm.doc.name });
        }, __("Open"));

        if (frm.doc.sandbox_completion_gate) {
            frm.add_custom_button(__("Open Sandbox Completion Gate"), () => {
                frappe.set_route("Form", "NDIS Accounting Sandbox Completion Gate", frm.doc.sandbox_completion_gate);
            }, __("Open"));
        }

        if (frm.doc.status !== "Cancelled") {
            frm.add_custom_button(__("Cancel Review"), () => {
                frappe.prompt([
                    { fieldname: "reason", label: __("Cancellation Reason"), fieldtype: "Small Text", reqd: 1 }
                ], (values) => {
                    frappe.call({
                        method: "ndis_finance.services.accounting_design_matrix.cancel_accounting_design_review",
                        args: { design_review: frm.doc.name, reason: values.reason },
                        freeze: true,
                        freeze_message: __("Cancelling design review..."),
                        callback() {
                            frm.reload_doc();
                        }
                    });
                }, __("Cancel Design Review"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
