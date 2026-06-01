frappe.listview_settings["NDIS Real Remittance PE Rollback Line"] = {
    get_indicator(doc) {
        if (doc.status === "Cancelled") return [__("Cancelled"), "green", "status,=,Cancelled"];
        if (doc.status === "Restored") return [__("Restored"), "green", "status,=,Restored"];
        if (doc.status === "Validated") return [__("Validated"), "blue", "status,=,Validated"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        return [__(doc.status || "Info"), "gray", `status,=,${doc.status || "Info"}`];
    }
};
