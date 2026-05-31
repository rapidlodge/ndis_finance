frappe.listview_settings["NDIS Real Remittance PE Design Gate"] = {
    get_indicator(doc) {
        if (doc.status === "Approved") return [__("Approved"), "green", "status,=,Approved"];
        if (doc.status === "Previewed") return [__("Previewed"), "blue", "status,=,Previewed"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
