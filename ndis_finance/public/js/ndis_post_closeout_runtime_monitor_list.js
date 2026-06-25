frappe.listview_settings["NDIS Post Closeout Runtime Monitor"] = {
    get_indicator(doc) {
        if (doc.status === "Monitor Active") return [__("Monitor Active"), "green", "status,=,Monitor Active"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
