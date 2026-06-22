frappe.listview_settings["NDIS Governed Limited Op Candidate Validation"] = {
    get_indicator(doc) {
        if (doc.status === "Candidate Validation Approved") return [__("Candidate Validation Approved"), "green", "status,=,Candidate Validation Approved"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
