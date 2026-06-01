frappe.listview_settings["NDIS Real Remittance PE Source Harness Line"] = {
    get_indicator(doc) {
        if (["Created", "Submitted", "Linked"].includes(doc.status)) return [__(doc.status), "green", `status,=,${doc.status}`];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
