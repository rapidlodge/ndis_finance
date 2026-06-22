frappe.listview_settings["NDIS Governed Next Op Preview"] = {
    get_indicator(doc) {
        if (doc.status === "Preview Approved") return [__("Preview Approved"), "green", "status,=,Preview Approved"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
