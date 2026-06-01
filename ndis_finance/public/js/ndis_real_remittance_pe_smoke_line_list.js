frappe.listview_settings["NDIS Real Remittance PE Smoke Line"] = {
    get_indicator(doc) {
        if (doc.status === "Submitted") return [__("Submitted"), "green", "status,=,Submitted"];
        if (doc.status === "Validated") return [__("Validated"), "green", "status,=,Validated"];
        if (doc.status === "Linked") return [__("Linked"), "blue", "status,=,Linked"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
