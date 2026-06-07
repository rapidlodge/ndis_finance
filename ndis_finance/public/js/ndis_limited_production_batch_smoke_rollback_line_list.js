frappe.listview_settings["NDIS Limited Production Batch Smoke Rollback Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Rolled Back") return [__("Rolled Back"), "green", "line_status,=,Rolled Back"];
        if (doc.line_status === "Blocked") return [__("Blocked"), "red", "line_status,=,Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Rolled Back"), "blue", `line_status,=,${doc.line_status || "Rolled Back"}`];
    }
};
