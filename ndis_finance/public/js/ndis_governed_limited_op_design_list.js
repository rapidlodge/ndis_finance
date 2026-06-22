frappe.listview_settings["NDIS Governed Limited Op Design"] = {
    get_indicator(doc) {
        if (doc.status === "Design Approved") return [__("Design Approved"), "green", "status,=,Design Approved"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
