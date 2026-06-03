frappe.listview_settings["NDIS Controlled Production Batch Smoke Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Submitted") return [__("Submitted"), "green", "line_status,=,Submitted"];
        if (doc.line_status === "Failed") return [__("Failed"), "red", "line_status,=,Failed"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Submitted"), "blue", `line_status,=,${doc.line_status || "Submitted"}`];
    }
};
