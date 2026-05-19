frappe.listview_settings["NDIS Executive Exception Action Step"] = {
    get_indicator(doc) {
        if (doc.status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Overdue") return [__("Overdue"), "red", "status,=,Overdue"];
        if (doc.status === "In Progress") return [__("In Progress"), "blue", "status,=,In Progress"];

        return [__(doc.status || "Open"), "orange", `status,=,${doc.status || "Open"}`];
    }
};
