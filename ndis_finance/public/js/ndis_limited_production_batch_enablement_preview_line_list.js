frappe.listview_settings["NDIS Limited Production Batch Enablement Preview Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Would Enable") return [__("Would Enable"), "blue", "line_status,=,Would Enable"];
        if (doc.line_status === "Blocked") return [__("Blocked"), "red", "line_status,=,Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Would Enable"), "blue", `line_status,=,${doc.line_status || "Would Enable"}`];
    }
};
