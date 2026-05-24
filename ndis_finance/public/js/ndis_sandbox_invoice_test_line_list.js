frappe.listview_settings["NDIS Sandbox Invoice Test Line"] = {
    get_indicator(doc) {
        if (doc.status === "Submitted") return [__("Submitted"), "green", "status,=,Submitted"];
        if (doc.status === "Created") return [__("Created"), "blue", "status,=,Created"];
        if (doc.status === "Reused") return [__("Reused"), "orange", "status,=,Reused"];
        if (doc.status === "Blocked") return [__("Blocked"), "red", "status,=,Blocked"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        return [__(doc.status || "Created"), "blue", `status,=,${doc.status || "Created"}`];
    }
};
