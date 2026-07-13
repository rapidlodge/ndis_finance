frappe.listview_settings["NDIS Next Governed Limited Op Rollback Freeze"] = {
    get_indicator(doc) {
        if (doc.status === "Freeze Completed") return [__("Freeze Completed"), "green", "status,=,Freeze Completed"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
