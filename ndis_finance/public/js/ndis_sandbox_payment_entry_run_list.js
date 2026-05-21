frappe.listview_settings["NDIS Sandbox Payment Entry Run"] = {
    get_indicator(doc) {
        if (doc.status === "Created Draft Payment Entry") return [__("Draft PE Created"), "green", "status,=,Created Draft Payment Entry"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
