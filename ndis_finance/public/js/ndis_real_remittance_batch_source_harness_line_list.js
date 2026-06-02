frappe.listview_settings["NDIS Real Remittance Batch Source Harness Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Ready") return [__("Ready"), "green", "line_status,=,Ready"];
        if (doc.line_status === "Needs Review") return [__("Needs Review"), "orange", "line_status,=,Needs Review"];
        if (doc.line_status === "Blocked") return [__("Blocked"), "red", "line_status,=,Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Ready"), "blue", `line_status,=,${doc.line_status || "Ready"}`];
    }
};
