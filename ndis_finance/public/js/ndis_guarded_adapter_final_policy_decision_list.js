frappe.listview_settings["NDIS Guarded Adapter Final Policy Decision"] = {
    get_indicator(doc) {
        if (doc.status === "Decision Applied") return [__("Decision Applied"), "green", "status,=,Decision Applied"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
