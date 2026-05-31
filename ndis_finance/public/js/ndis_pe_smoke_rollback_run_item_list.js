frappe.listview_settings["NDIS PE Smoke Rollback Run Item"] = {
    get_indicator(doc) {
        if (doc.status === "Pass") return [__("Pass"), "green", "status,=,Pass"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        if (doc.status === "Blocker") return [__("Blocker"), "red", "status,=,Blocker"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
