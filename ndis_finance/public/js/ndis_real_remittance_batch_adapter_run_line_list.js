frappe.listview_settings["NDIS Real Remittance Batch Adapter Run Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Hard Blocked") return [__("Hard Blocked"), "green", "line_status,=,Hard Blocked"];
        if (doc.line_status === "Validation Blocked") return [__("Validation Blocked"), "orange", "line_status,=,Validation Blocked"];
        if (doc.line_status === "Duplicate Blocked") return [__("Duplicate Blocked"), "orange", "line_status,=,Duplicate Blocked"];
        if (doc.line_status === "Cap Blocked") return [__("Cap Blocked"), "orange", "line_status,=,Cap Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Info"), "blue", `line_status,=,${doc.line_status || "Info"}`];
    }
};
