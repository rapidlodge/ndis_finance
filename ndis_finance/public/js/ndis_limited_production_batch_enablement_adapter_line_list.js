frappe.listview_settings["NDIS Limited Production Batch Enablement Adapter Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Hard Blocked") return [__("Hard Blocked"), "green", "line_status,=,Hard Blocked"];
        if (doc.line_status === "Validation Blocked") return [__("Validation Blocked"), "orange", "line_status,=,Validation Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Hard Blocked"), "blue", `line_status,=,${doc.line_status || "Hard Blocked"}`];
    }
};
