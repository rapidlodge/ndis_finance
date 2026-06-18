frappe.listview_settings["NDIS Runtime Watch Violation Sim"] = {
    get_indicator(doc) {
        if (doc.status === "Simulation Completed") return [__("Simulation Completed"), "green", "status,=,Simulation Completed"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
