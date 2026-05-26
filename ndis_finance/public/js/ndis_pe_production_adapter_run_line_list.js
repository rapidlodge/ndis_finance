frappe.listview_settings["NDIS PE Production Adapter Run Line"] = {
    get_indicator(doc) {
        if (doc.status === "Hard Blocked") return [__("Hard Blocked"), "green", "status,=,Hard Blocked"];
        if (doc.status === "Validation Blocked") return [__("Validation Blocked"), "orange", "status,=,Validation Blocked"];
        if (doc.status === "Duplicate Blocked") return [__("Duplicate Blocked"), "orange", "status,=,Duplicate Blocked"];
        if (doc.status === "Rejected Blocked") return [__("Rejected Blocked"), "orange", "status,=,Rejected Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
