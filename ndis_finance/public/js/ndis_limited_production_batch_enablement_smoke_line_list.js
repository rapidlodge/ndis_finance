frappe.listview_settings["NDIS Limited Production Batch Enablement Smoke Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Enabled - Rollback Required") return [__("Rollback Required"), "orange", "line_status,=,Enabled - Rollback Required"];
        if (doc.line_status === "Preview Only") return [__("Preview Only"), "blue", "line_status,=,Preview Only"];
        if (doc.line_status === "Blocked") return [__("Blocked"), "red", "line_status,=,Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Preview Only"), "blue", `line_status,=,${doc.line_status || "Preview Only"}`];
    }
};
