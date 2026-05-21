frappe.listview_settings["NDIS Payment Entry Mapping Rule"] = {
    get_indicator(doc) {
        if (doc.status === "Active") return [__("Active"), "green", "status,=,Active"];
        if (doc.status === "Draft") return [__("Draft"), "blue", "status,=,Draft"];
        if (doc.status === "Suspended") return [__("Suspended"), "orange", "status,=,Suspended"];
        if (doc.status === "Retired") return [__("Retired"), "gray", "status,=,Retired"];
        return [__(doc.status || "Draft"), "blue", `status,=,${doc.status || "Draft"}`];
    }
};
