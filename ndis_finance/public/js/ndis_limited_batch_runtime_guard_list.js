frappe.listview_settings["NDIS Limited Batch Runtime Guard"] = {
    get_indicator(doc) {
        if (doc.status === "Guarded") return [__("Guarded"), "green", "status,=,Guarded"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
