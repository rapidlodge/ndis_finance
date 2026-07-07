frappe.listview_settings["NDIS Next Governed Limited Op Candidate Selection"] = {
    get_indicator(doc) {
        if (doc.status === "Candidate Selection Approved") return [__("Candidate Selection Approved"), "green", "status,=,Candidate Selection Approved"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
