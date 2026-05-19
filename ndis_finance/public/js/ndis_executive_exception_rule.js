frappe.ui.form.on("NDIS Executive Exception Rule", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Alerts"), () => {
            frappe.set_route("List", "NDIS Executive Exception Alert", {
                rule: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Evaluate This Rule"), () => {
            frappe.call({
                method: "ndis_finance.services.executive_exceptions.evaluate_executive_exception_rules",
                args: {
                    rule: frm.doc.name,
                    dry_run: 0
                },
                freeze: true,
                freeze_message: __("Evaluating exception rule..."),
                callback() {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Rule evaluated. Internal alert may have been created."),
                        indicator: "blue"
                    });
                }
            });
        }, __("NDIS Actions"));

        frm.add_custom_button(__("Dry Run This Rule"), () => {
            frappe.call({
                method: "ndis_finance.services.executive_exceptions.evaluate_executive_exception_rules",
                args: {
                    rule: frm.doc.name,
                    dry_run: 1
                },
                freeze: true,
                freeze_message: __("Dry-running exception rule..."),
                callback(r) {
                    frappe.msgprint({
                        title: __("Dry Run Result"),
                        message: `<pre>${JSON.stringify(r.message || {}, null, 2)}</pre>`,
                        indicator: "blue"
                    });
                }
            });
        }, __("NDIS Actions"));
    }
});
