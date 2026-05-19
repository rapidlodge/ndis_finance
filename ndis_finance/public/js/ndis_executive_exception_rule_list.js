frappe.listview_settings["NDIS Executive Exception Rule"] = {
    get_indicator(doc) {
        if (!doc.active) return [__("Inactive"), "gray", "active,=,0"];
        if (doc.severity === "Critical") return [__("Critical"), "red", "severity,=,Critical"];
        if (doc.severity === "High") return [__("High"), "orange", "severity,=,High"];
        if (doc.severity === "Medium") return [__("Medium"), "yellow", "severity,=,Medium"];

        return [__("Low"), "blue", "severity,=,Low"];
    }
};
