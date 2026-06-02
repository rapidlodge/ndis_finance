frappe.listview_settings["NDIS Real Remittance Batch Preview Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Eligible") return [__("Eligible"), "green", "line_status,=,Eligible"];
        if (doc.line_status === "Blocked") return [__("Blocked"), "red", "line_status,=,Blocked"];
        if (doc.line_status === "Duplicate") return [__("Duplicate"), "orange", "line_status,=,Duplicate"];
        if (doc.line_status === "Cap Blocked") return [__("Cap Blocked"), "orange", "line_status,=,Cap Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Info"), "blue", `line_status,=,${doc.line_status || "Info"}`];
    }
};
