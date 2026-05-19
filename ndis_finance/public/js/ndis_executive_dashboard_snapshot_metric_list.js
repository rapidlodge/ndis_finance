frappe.listview_settings["NDIS Executive Dashboard Snapshot Metric"] = {
    get_indicator(doc) {
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.risk_status === "Risk") return [__("Risk"), "red", "risk_status,=,Risk"];
        if (doc.risk_status === "Watch") return [__("Watch"), "orange", "risk_status,=,Watch"];
        if (doc.risk_status === "Good") return [__("Good"), "green", "risk_status,=,Good"];

        return [__(doc.risk_status || "Info"), "blue", `risk_status,=,${doc.risk_status || "Info"}`];
    }
};
