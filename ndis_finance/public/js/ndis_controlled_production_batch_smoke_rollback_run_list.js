frappe.listview_settings["NDIS Controlled Production Batch Smoke Rollback Run"] = {
    get_indicator(doc) {
        if (doc.status === "Rolled Back") return [__("Rolled Back"), "green", "status,=,Rolled Back"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};