frappe.listview_settings["NDIS Sandbox Payment Entry Cleanup Line"] = {
    get_indicator(doc) {
        if (doc.status === "Deleted") return [__("Deleted"), "green", "status,=,Deleted"];
        if (doc.status === "Eligible") return [__("Eligible"), "blue", "status,=,Eligible"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Candidate"), "blue", `status,=,${doc.status || "Candidate"}`];
    }
};
