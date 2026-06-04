frappe.listview_settings["NDIS Controlled Production Batch Smoke Rollback Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Restored") return [__("Restored"), "green", "line_status,=,Restored"];
        if (doc.line_status === "Failed") return [__("Failed"), "red", "line_status,=,Failed"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Restored"), "blue", `line_status,=,${doc.line_status || "Restored"}`];
    }
};