frappe.listview_settings["NDIS Real Remittance Batch PE Smoke Line"] = {
    get_indicator(doc) {
        if (doc.line_status === "Submitted") return [__("Submitted"), "green", "line_status,=,Submitted"];
        if (doc.line_status === "Needs Review") return [__("Needs Review"), "orange", "line_status,=,Needs Review"];
        if (doc.line_status === "Blocked") return [__("Blocked"), "red", "line_status,=,Blocked"];
        if (doc.line_status === "Cancelled") return [__("Cancelled"), "gray", "line_status,=,Cancelled"];
        return [__(doc.line_status || "Submitted"), "blue", `line_status,=,${doc.line_status || "Submitted"}`];
    }
};
