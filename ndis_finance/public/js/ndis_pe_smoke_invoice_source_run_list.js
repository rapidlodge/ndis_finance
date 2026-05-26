frappe.listview_settings["NDIS PE Smoke Invoice Source Run"] = {
    get_indicator(doc) {
        if (doc.status === "Source Created") return [__("Source Created"), "green", "status,=,Source Created"];
        if (doc.status === "Previewed") return [__("Previewed"), "blue", "status,=,Previewed"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Source Cancelled") return [__("Source Cancelled"), "gray", "status,=,Source Cancelled"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
