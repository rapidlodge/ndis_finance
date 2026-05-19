frappe.listview_settings["NDIS Executive Governance Pack"] = {
    get_indicator(doc) {
        if (doc.status === "Signed Off") return [__("Signed Off"), "green", "status,=,Signed Off"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];

        if (doc.governance_status === "Critical") return [__("Critical"), "red", "governance_status,=,Critical"];
        if (doc.governance_status === "Needs Attention") return [__("Needs Attention"), "orange", "governance_status,=,Needs Attention"];
        if (doc.governance_status === "Watch") return [__("Watch"), "yellow", "governance_status,=,Watch"];
        if (doc.governance_status === "Strong") return [__("Strong"), "green", "governance_status,=,Strong"];

        return [__(doc.status || "Generated"), "blue", `status,=,${doc.status || "Generated"}`];
    }
};
