frappe.listview_settings["NDIS Executive Exception Action Plan"] = {
    get_indicator(doc) {
        if (doc.status === "Completed") return [__("Completed"), "green", "status,=,Completed"];
        if (doc.status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];
        if (doc.status === "Overdue") return [__("Overdue"), "red", "status,=,Overdue"];
        if (doc.status === "Escalated") return [__("Escalated"), "orange", "status,=,Escalated"];
        if (doc.priority === "Critical") return [__("Critical"), "red", "priority,=,Critical"];
        if (doc.priority === "High") return [__("High"), "orange", "priority,=,High"];

        return [__(doc.status || "In Progress"), "blue", `status,=,${doc.status || "In Progress"}`];
    }
};
