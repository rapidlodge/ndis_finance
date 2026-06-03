frappe.listview_settings["NDIS Controlled Production Batch Adapter Run"] = {
    get_indicator(doc) {
        if (doc.status === "Hard Blocked") return [__("Hard Blocked"), "green", "status,=,Hard Blocked"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
