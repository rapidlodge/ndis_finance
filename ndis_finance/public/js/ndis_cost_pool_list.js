frappe.listview_settings["NDIS Cost Pool"] = {
    get_indicator(doc) {
        const status = doc.status;

        if (status === "Allocated") return [__("Allocated"), "green", "status,=,Allocated"];
        if (status === "Partially Allocated") return [__("Partially Allocated"), "orange", "status,=,Partially Allocated"];
        if (status === "Cancelled") return [__("Cancelled"), "gray", "status,=,Cancelled"];

        return [__(status || "Draft"), "orange", `status,=,${status || "Draft"}`];
    },
};
