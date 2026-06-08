frappe.listview_settings["NDIS Limited Production Batch Enablement Smoke Run"] = {
    get_indicator(doc) {
        if (doc.status === "Enabled - Rollback Required") return [__("Rollback Required"), "orange", "status,=,Enabled - Rollback Required"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Source Pending") return [__("Source Pending"), "orange", "status,=,Source Pending"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
