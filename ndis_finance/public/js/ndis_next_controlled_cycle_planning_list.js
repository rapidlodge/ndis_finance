frappe.listview_settings["NDIS Next Controlled Cycle Planning"] = {
    get_indicator(doc) {
        if (doc.status === "Planning Approved") return [__("Planning Approved"), "green", "status,=,Planning Approved"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
