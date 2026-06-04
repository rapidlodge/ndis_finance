frappe.listview_settings["NDIS Controlled Production Batch Policy Review Gate"] = {
    get_indicator(doc) {
        if (doc.status === "Approved For Limited Policy Design") return [__("Approved"), "green", "status,=,Approved For Limited Policy Design"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
