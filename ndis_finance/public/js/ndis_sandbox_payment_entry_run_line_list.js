frappe.listview_settings["NDIS Sandbox Payment Entry Run Line"] = {
    get_indicator(doc) {
        if (doc.status === "Included In Draft PE") return [__("Included"), "green", "status,=,Included In Draft PE"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Duplicate") return [__("Duplicate"), "red", "status,=,Duplicate"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Excluded"), "orange", `status,=,${doc.status || "Excluded"}`];
    }
};
