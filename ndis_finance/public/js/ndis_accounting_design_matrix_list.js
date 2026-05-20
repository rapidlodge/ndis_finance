frappe.listview_settings["NDIS Accounting Design Matrix"] = {
    get_indicator(doc) {
        if (doc.design_status === "Suspended") return [__("Suspended"), "orange", "design_status,=,Suspended"];
        if (doc.design_status === "Retired") return [__("Retired"), "gray", "design_status,=,Retired"];
        if (doc.risk_level === "Critical") return [__("Critical"), "red", "risk_level,=,Critical"];
        if (doc.risk_level === "High") return [__("High Risk"), "orange", "risk_level,=,High"];
        if (doc.design_status === "Active") return [__("Active"), "green", "design_status,=,Active"];
        return [__(doc.design_status || "Draft"), "blue", `design_status,=,${doc.design_status || "Draft"}`];
    }
};
