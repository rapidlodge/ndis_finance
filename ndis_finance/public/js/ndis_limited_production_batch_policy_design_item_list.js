frappe.listview_settings["NDIS Limited Production Batch Policy Design Item"] = {
    get_indicator(doc) {
        if (doc.rule_status === "Designed") return [__("Designed"), "green", "rule_status,=,Designed"];
        if (doc.rule_status === "Blocked") return [__("Blocked"), "red", "rule_status,=,Blocked"];
        if (doc.rule_status === "Cancelled") return [__("Cancelled"), "gray", "rule_status,=,Cancelled"];
        return [__(doc.rule_status || "Designed"), "blue", `rule_status,=,${doc.rule_status || "Designed"}`];
    }
};
