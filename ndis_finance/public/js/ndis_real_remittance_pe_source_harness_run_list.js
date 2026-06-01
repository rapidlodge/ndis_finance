frappe.listview_settings["NDIS Real Remittance PE Source Harness Run"] = {
    get_indicator(doc) {
        if (doc.status === "Source Ready") return [__("Source Ready"), "green", "status,=,Source Ready"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
