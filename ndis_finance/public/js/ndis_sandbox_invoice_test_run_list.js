frappe.listview_settings["NDIS Sandbox Invoice Test Run"] = {
    get_indicator(doc) {
        if (doc.status === "Submitted Invoice Created") return [__("Submitted Sandbox SI"), "green", "status,=,Submitted Invoice Created"];
        if (doc.status === "Created Draft Invoice") return [__("Draft Sandbox SI"), "blue", "status,=,Created Draft Invoice"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
