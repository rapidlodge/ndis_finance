frappe.listview_settings["NDIS Next Governed Limited Op Exec Gate"] = {
    get_indicator(doc) {
        if (doc.status === "Execution Gate Approved") return [__("Execution Gate Approved"), "green", "status,=,Execution Gate Approved"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
