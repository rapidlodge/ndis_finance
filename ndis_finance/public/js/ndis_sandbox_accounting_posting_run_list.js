frappe.listview_settings["NDIS Sandbox Accounting Posting Run"] = {
    get_indicator(doc) {
        if (doc.status === "Created Draft JE") return [__("Draft JE Created"), "green", "status,=,Created Draft JE"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
