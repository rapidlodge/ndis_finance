frappe.listview_settings["NDIS PE One Submitted Smoke Run"] = {
    get_indicator(doc) {
        if (doc.status === "Submitted") return [__("Submitted"), "green", "status,=,Submitted"];
        if (doc.status === "Payment Cancelled") return [__("Payment Cancelled"), "gray", "status,=,Payment Cancelled"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
