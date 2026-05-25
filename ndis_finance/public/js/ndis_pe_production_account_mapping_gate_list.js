frappe.listview_settings["NDIS PE Production Account Mapping Gate"] = {
    get_indicator(doc) {
        if (doc.status === "Hardened") return [__("Hardened"), "green", "status,=,Hardened"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
