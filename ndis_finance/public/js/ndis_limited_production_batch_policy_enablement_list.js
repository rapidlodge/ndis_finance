frappe.listview_settings["NDIS Limited Production Batch Policy Enablement Run"] = {
    get_indicator(doc) {
        if (doc.status === "Enabled - Final Rollback Optional") return [__("Enabled"), "green", "status,=,Enabled - Final Rollback Optional"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
