frappe.ui.form.on("NDIS Executive Dashboard Snapshot", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Open Metrics"), () => {
            frappe.set_route("List", "NDIS Executive Dashboard Snapshot Metric", {
                snapshot: frm.doc.name
            });
        }, __("Open"));

        frm.add_custom_button(__("Open Trend Report"), () => {
            frappe.set_route("query-report", "NDIS Executive KPI Trend Report");
        }, __("Open"));

        frm.add_custom_button(__("Open Detail Report"), () => {
            frappe.set_route("query-report", "NDIS Executive Snapshot Detail Report", {
                snapshot: frm.doc.name
            });
        }, __("Open"));

        if (frm.doc.status === "Active") {
            frm.add_custom_button(__("Cancel Snapshot"), () => {
                frappe.prompt([
                    {
                        fieldname: "reason",
                        label: __("Cancellation Reason"),
                        fieldtype: "Small Text",
                        reqd: 1
                    }
                ], (values) => {
                    frappe.confirm(
                        __("This cancels the snapshot record only. It does not change any finance, payroll, recovery, or accounting record. Continue?"),
                        () => {
                            frappe.call({
                                method: "ndis_finance.services.executive_snapshots.cancel_executive_dashboard_snapshot",
                                args: {
                                    snapshot: frm.doc.name,
                                    reason: values.reason
                                },
                                freeze: true,
                                freeze_message: __("Cancelling snapshot..."),
                                callback() {
                                    frm.reload_doc();
                                    frappe.show_alert({
                                        message: __("Executive snapshot cancelled only."),
                                        indicator: "gray"
                                    });
                                }
                            });
                        }
                    );
                }, __("Cancel Snapshot"), __("Cancel"));
            }, __("NDIS Actions"));
        }
    }
});
