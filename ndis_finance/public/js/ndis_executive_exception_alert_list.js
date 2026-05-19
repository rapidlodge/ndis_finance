frappe.listview_settings["NDIS Executive Exception Alert"] = {
    get_indicator(doc) {
        if (doc.status === "Resolved") return [__("Resolved"), "green", "status,=,Resolved"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.severity === "Critical") return [__("Critical"), "red", "severity,=,Critical"];
        if (doc.severity === "High") return [__("High"), "orange", "severity,=,High"];
        if (doc.severity === "Medium") return [__("Medium"), "yellow", "severity,=,Medium"];

        return [__(doc.status || "Open"), "blue", `status,=,${doc.status || "Open"}`];
    }
};
