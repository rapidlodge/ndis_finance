frappe.listview_settings["NDIS PE Submitted Smoke Gate"] = {
    get_indicator(doc) {
        if (doc.status === "Source Ready") return [__("Source Ready"), "green", "status,=,Source Ready"];
        if (doc.status === "Source Pending") return [__("Source Pending"), "orange", "status,=,Source Pending"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
