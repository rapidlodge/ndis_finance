frappe.listview_settings["NDIS PE Smoke Rollback Run"] = {
    get_indicator(doc) {
        if (doc.status === "Fully Rolled Back") return [__("Fully Rolled Back"), "green", "status,=,Fully Rolled Back"];
        if (doc.status === "Payment Entry Cancelled") return [__("Payment Entry Cancelled"), "green", "status,=,Payment Entry Cancelled"];
        if (doc.status === "Previewed") return [__("Previewed"), "blue", "status,=,Previewed"];
        if (doc.status === "Needs Review") return [__("Needs Review"), "orange", "status,=,Needs Review"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
