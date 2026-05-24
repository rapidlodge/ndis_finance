frappe.listview_settings["NDIS Invoice Backed PE Smoke Run"] = {
    get_indicator(doc) {
        if (doc.status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
