frappe.ui.form.on("NDIS Recovery Automation Log", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Health Report"), () => {
            frappe.set_route("query-report", "NDIS Automation Health Report");
        }, __("Reports"));

        frm.add_custom_button(__("Open Exception Report"), () => {
            frappe.set_route("query-report", "NDIS Automation Exception Report");
        }, __("Reports"));

        frm.add_custom_button(__("Run Manual Preview"), () => {
            frappe.call({
                method: "ndis_finance.services.recovery_scheduler.run_daily_recovery_monitor",
                args: {
                    run_type: "Manual",
                    create_missing_cases: 0,
                    preview_limit: 20,
                },
                freeze: true,
                freeze_message: __("Running manual preview..."),
                callback(r) {
                    frappe.show_alert({
                        message: __("Manual preview completed. No emails or accounting actions were created."),
                        indicator: "green",
                    });

                    if (r.message && r.message.automation_log) {
                        frappe.set_route("Form", "NDIS Recovery Automation Log", r.message.automation_log);
                    }
                },
            });
        }, __("Automation"));

        frm.add_custom_button(__("Run Monitor + Create Missing Cases"), () => {
            frappe.confirm(
                __("This will create missing recovery cases from open leakage records only. It will not send emails or create accounting entries. Continue?"),
                () => {
                    frappe.call({
                        method: "ndis_finance.services.recovery_scheduler.run_daily_recovery_monitor",
                        args: {
                            run_type: "Manual",
                            create_missing_cases: 1,
                            preview_limit: 20,
                        },
                        freeze: true,
                        freeze_message: __("Running recovery monitor..."),
                        callback(r) {
                            frappe.show_alert({
                                message: __("Recovery monitor completed. No emails or accounting entries were created."),
                                indicator: "green",
                            });

                            if (r.message && r.message.automation_log) {
                                frappe.set_route("Form", "NDIS Recovery Automation Log", r.message.automation_log);
                            }
                        },
                    });
                }
            );
        }, __("Automation"));
    },
});
