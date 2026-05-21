frappe.listview_settings["NDIS Sandbox Payment Entry Cleanup Run"] = {
    get_indicator(doc) {
        if (doc.status === "Cleaned") return [__("Cleaned"), "green", "status,=,Cleaned"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        return [__(doc.status || "Previewed"), "blue", `status,=,${doc.status || "Previewed"}`];
    }
};
