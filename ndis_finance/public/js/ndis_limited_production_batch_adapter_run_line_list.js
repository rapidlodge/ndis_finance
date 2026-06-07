frappe.listview_settings["NDIS Limited Production Batch Adapter Run Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Hard Blocked") return [__("Hard Blocked"), "green", "line_status,=,Hard Blocked"];
        if (doc.line_status === "Validation Blocked") return [__("Validation Blocked"), "red", "line_status,=,Validation Blocked"];
        if (doc.line_status === "Duplicate Blocked") return [__("Duplicate Blocked"), "orange", "line_status,=,Duplicate Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Hard Blocked"), "blue", `line_status,=,${doc.line_status || "Hard Blocked"}`];
    }
};
