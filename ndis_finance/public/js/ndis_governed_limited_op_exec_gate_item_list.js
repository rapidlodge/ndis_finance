frappe.listview_settings["NDIS Governed Limited Op Exec Gate Item"] = {
    get_indicator(doc) {
        if (doc.status === "Pass") return [__("Pass"), "green", "status,=,Pass"];
        if (doc.status === "Warning") return [__("Warning"), "orange", "status,=,Warning"];
        if (doc.status === "Blocker") return [__("Blocker"), "red", "status,=,Blocker"];
        return [__(doc.status || "Info"), "blue", `status,=,${doc.status || "Info"}`];
    }
};
