frappe.listview_settings["NDIS Guarded Limited Adapter Smoke"] = {
    get_indicator(doc) {
        if (doc.status === "Smoke Completed - Rollback Required") return [__("Rollback Required"), "orange", "status,=,Smoke Completed - Rollback Required"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
