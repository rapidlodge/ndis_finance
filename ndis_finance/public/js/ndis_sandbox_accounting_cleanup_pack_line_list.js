frappe.listview_settings["NDIS Sandbox Accounting Cleanup Pack Line"] = {
    get_indicator(doc) {
        if (doc.status === "Deleted") return [__("Deleted"), "green", "status,=,Deleted"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "green", "status,=,Cancelled"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
