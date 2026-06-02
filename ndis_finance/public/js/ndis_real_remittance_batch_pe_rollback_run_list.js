frappe.listview_settings["NDIS Real Remittance Batch PE Rollback Run"] = {
    get_indicator(doc) {
        if (doc.status === "Rolled Back") return [__("Rolled Back"), "green", "status,=,Rolled Back"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
