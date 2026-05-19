frappe.listview_settings["NDIS Executive Dashboard Snapshot"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Create Snapshot"), () => {
            frappe.call({
                method: "ndis_finance.services.executive_snapshots.create_executive_dashboard_snapshot",
                args: {
                    snapshot_type: "Manual",
                    replace_existing: 0,
                    notes: "Manual snapshot from list view."
                },
                freeze: true,
                freeze_message: __("Creating executive dashboard snapshot..."),
                callback(r) {
                    if (r.message && r.message.snapshot) {
                        frappe.set_route("Form", "NDIS Executive Dashboard Snapshot", r.message.snapshot);
                    }
                    listview.refresh();
                }
            });
        });
    },

    get_indicator(doc) {
        if (doc.status === "Active") return [__("Active"), "green", "status,=,Active"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];

        return [__(doc.status || "Active"), "blue", `status,=,${doc.status || "Active"}`];
    }
};
