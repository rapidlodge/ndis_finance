frappe.listview_settings["NDIS Sandbox Accounting Cleanup Pack"] = {
    get_indicator(doc) {
        if (doc.status === "Cleaned") return [__("Cleaned"), "green", "status,=,Cleaned"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
