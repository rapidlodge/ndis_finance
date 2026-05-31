frappe.listview_settings["NDIS Real Remittance PE Preview Line"] = {
    get_indicator(doc) {
        if (doc.preview_status === "Eligible") return [__("Eligible"), "green", "preview_status,=,Eligible"];
        if (doc.preview_status === "Blocked") return [__("Blocked"), "red", "preview_status,=,Blocked"];
        if (doc.preview_status === "Review") return [__("Review"), "orange", "preview_status,=,Review"];
        if (doc.preview_status === "Cancelled") return [__("Cancelled"), "gray", "preview_status,=,Cancelled"];
        return [__(doc.preview_status || "Review"), "orange", `preview_status,=,${doc.preview_status || "Review"}`];
    }
};
