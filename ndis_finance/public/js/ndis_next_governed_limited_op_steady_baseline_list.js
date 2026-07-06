frappe.listview_settings["NDIS Next Governed Limited Op Steady Baseline"] = {
    get_indicator(doc) {
        if (doc.status === "Baseline Active") return [__("Baseline Active"), "green", "status,=,Baseline Active"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
